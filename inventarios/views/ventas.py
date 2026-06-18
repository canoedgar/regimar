from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from accounts.decorators import grupos_requeridos, permiso_requerido
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.forms import modelformset_factory

from catalogos.models import Almacen, Producto, Cliente
from catalogos.services.clientes_precios import registrar_ultimo_precio_cliente
from ..models import SalidaInventario, SalidaInventarioDetalle, SalidaInventarioDetalleAlmacen
from ..forms import SalidaVentaEdicionForm, SalidaVentaDetallePrecioForm, SalidaInventarioDetalleForm
from ..services.stock import aplicar_movimiento_stock, aplicar_movimientos_salida
from ..services.venta_parser import VentaPostParser
from ..services.ventas import VentaService
from ..selectors.ventas import get_contexto_salida_venta


def _importe_expr():
    """
    Importe comercial de una línea de venta.

    Regla única del módulo:
    - cantidad = cantidad ya convertida a la métrica base que afecta inventario (kg/base).
    - precio_unitario = precio por la métrica base (precio por kg/base).
    - cantidad_presentacion solo sirve para mostrar la captura original (cajas, piezas, etc.).

    Por eso el importe NUNCA debe calcularse con cantidad_presentacion.
    """
    return ExpressionWrapper(
        F("cantidad") * F("precio_unitario"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )


def _importe_detalles_expr():
    """Misma regla anterior, aplicada desde SalidaInventario hacia sus detalles."""
    return ExpressionWrapper(
        F("detalles__cantidad") * F("detalles__precio_unitario"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )


def _base_detalles_qs(request):
    qs = (
        SalidaInventarioDetalle.objects
        .select_related("producto", "almacen")
        .prefetch_related("asignaciones__almacen")
        .annotate(importe=_importe_expr())
        .order_by("id")
    )

    producto_id = (request.GET.get("producto") or "").strip()
    presentacion = (request.GET.get("presentacion") or "").strip()
    almacen_id = (request.GET.get("almacen") or "").strip()

    if producto_id.isdigit():
        qs = qs.filter(producto_id=int(producto_id))

    if presentacion:
        qs = qs.filter(presentacion_nombre__icontains=presentacion)

    if almacen_id.isdigit():
        qs = qs.filter(
            Q(almacen_id=int(almacen_id)) |
            Q(asignaciones__almacen_id=int(almacen_id)) |
            Q(salida__almacen_id=int(almacen_id))
        ).distinct()

    return qs


@permiso_requerido("inventarios.view_salidainventario")
def ventas_list(request):
    """
    Vista especializada de notas de venta:
    - muestra notas y detalle por nota
    - filtra por folio, cliente, producto, presentación, almacén, fechas y estado
    - permite imprimir/descargar una o varias notas
    - expone acción de cancelación
    """
    ventas = (
        SalidaInventario.objects
        .filter(tipo=SalidaInventario.TIPO_VENTA)
        .select_related("almacen", "cliente_ref")
        .order_by("-fecha", "-folio")
    )

    folio = (request.GET.get("folio") or "").strip()
    cliente = (request.GET.get("cliente") or "").strip()
    fecha_inicio = (request.GET.get("fecha_inicio") or "").strip()
    fecha_fin = (request.GET.get("fecha_fin") or "").strip()
    estado = (request.GET.get("estado") or "").strip()
    estado_pago = (request.GET.get("estado_pago") or "").strip()

    # Al entrar al listado sin filtros, se muestran automáticamente las notas del día.
    if not request.GET:
        hoy = timezone.localdate().isoformat()
        fecha_inicio = hoy
        fecha_fin = hoy
    producto_id = (request.GET.get("producto") or "").strip()
    almacen_id = (request.GET.get("almacen") or "").strip()
    presentacion = (request.GET.get("presentacion") or "").strip()

    if folio:
        ventas = ventas.filter(folio__icontains=folio)
    if cliente:
        ventas = ventas.filter(cliente__icontains=cliente)
    if fecha_inicio:
        ventas = ventas.filter(fecha__gte=fecha_inicio)
    if fecha_fin:
        ventas = ventas.filter(fecha__lte=fecha_fin)
    if estado in dict(SalidaInventario.ESTADO_CHOICES):
        ventas = ventas.filter(estado=estado)
    if estado_pago in dict(SalidaInventario.ESTADO_PAGO_CHOICES):
        ventas = ventas.filter(estado_pago=estado_pago)
    if producto_id.isdigit():
        ventas = ventas.filter(detalles__producto_id=int(producto_id))
    if almacen_id.isdigit():
        ventas = ventas.filter(
            Q(almacen_id=int(almacen_id)) |
            Q(detalles__almacen_id=int(almacen_id)) |
            Q(detalles__asignaciones__almacen_id=int(almacen_id))
        )
    if presentacion:
        ventas = ventas.filter(detalles__presentacion_nombre__icontains=presentacion)

    ventas = ventas.distinct().annotate(
        total_cantidad=Sum("detalles__cantidad"),
        total_importe=Sum(_importe_detalles_expr()),
        num_detalle_almacenes=Count("detalles__almacen", distinct=True),
        num_asignacion_almacenes=Count("detalles__asignaciones__almacen", distinct=True),
    )

    # Guardamos los IDs de las ventas activas filtradas antes de paginar.
    # Los KPIs/resúmenes no deben considerar notas canceladas.
    ventas_activas_ids = list(
        ventas.exclude(estado=SalidaInventario.ESTADO_CANCELADA)
        .values_list("id", flat=True)
    )

    resumen = SalidaInventarioDetalle.objects.filter(
        salida_id__in=ventas_activas_ids
    ).aggregate(
        total_cantidad=Sum("cantidad"),
        total_notas=Sum(_importe_expr()),
    )

    detalle_qs = _base_detalles_qs(request)
    ventas = ventas.prefetch_related(
        Prefetch("detalles", queryset=detalle_qs, to_attr="detalles_filtrados")
    )

    paginator = Paginator(ventas, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Etiqueta visual de almacén por nota:
    # - si se usaron varios almacenes, mostrar "Varios"
    # - si solo hay uno, mostrar su código/nombre
    # - si no hay dato, mostrar guion en template
    for venta in page_obj.object_list:
        almacenes_por_id = {}
        if getattr(venta, "almacen_id", None) and getattr(venta, "almacen", None):
            almacenes_por_id[venta.almacen_id] = venta.almacen

        for detalle in getattr(venta, "detalles_filtrados", []):
            almacen_detalle = getattr(detalle, "almacen", None)
            if getattr(detalle, "almacen_id", None) and almacen_detalle:
                almacenes_por_id[detalle.almacen_id] = almacen_detalle

            for asignacion in getattr(detalle, "asignaciones", []).all():
                almacen_asignacion = getattr(asignacion, "almacen", None)
                if getattr(asignacion, "almacen_id", None) and almacen_asignacion:
                    almacenes_por_id[asignacion.almacen_id] = almacen_asignacion

        almacenes_unicos = list(almacenes_por_id.values())
        venta.almacen_es_multiple = len(almacenes_unicos) > 1
        venta.almacen_codigo_display = almacenes_unicos[0].codigo if len(almacenes_unicos) == 1 else ""
        venta.almacen_nombre_display = almacenes_unicos[0].nombre if len(almacenes_unicos) == 1 else ""

    filtros = request.GET.copy()
    if not request.GET:
        filtros["fecha_inicio"] = fecha_inicio
        filtros["fecha_fin"] = fecha_fin

    querystring = filtros.copy()
    querystring.pop("page", None)

    context = {
        "page_obj": page_obj,
        "ventas": page_obj.object_list,
        "productos": Producto.objects.all().order_by("nombre"),
        "almacenes": Almacen.objects.filter(es_activo=True).order_by("tipo", "nombre"),
        "estado_choices": SalidaInventario.ESTADO_CHOICES,
        "estado_pago_choices": SalidaInventario.ESTADO_PAGO_CHOICES,
        "filtros": filtros,
        "querystring": querystring.urlencode(),
        "total_notas": resumen["total_notas"] or Decimal("0"),
        "total_cantidad": resumen["total_cantidad"] or Decimal("0"),
    }
    return render(request, "inventarios/ventas_list.html", context)



def _hay_productos_nuevos_en_post(request, prefix="nuevos"):
    try:
        total = int(request.POST.get(f"{prefix}-TOTAL_FORMS", "0") or 0)
    except (TypeError, ValueError):
        return False

    for idx in range(total):
        if (request.POST.get(f"{prefix}-{idx}-producto") or "").strip():
            return True
    return False



def _productos_nuevos_repetidos_en_nota(request, salida, prefix="nuevos"):
    """
    Evita agregar en edición productos que ya existen en la nota.
    La regla es por producto, sin importar presentación o almacén.
    """
    productos_existentes = set(
        salida.detalles.values_list("producto_id", flat=True)
    )

    try:
        total = int(request.POST.get(f"{prefix}-TOTAL_FORMS", "0") or 0)
    except (TypeError, ValueError):
        return []

    repetidos = []
    vistos_en_post = set()

    for idx in range(total):
        raw_producto_id = (request.POST.get(f"{prefix}-{idx}-producto") or "").strip()
        if not raw_producto_id.isdigit():
            continue

        producto_id = int(raw_producto_id)
        if producto_id in productos_existentes or producto_id in vistos_en_post:
            repetidos.append(producto_id)
        vistos_en_post.add(producto_id)

    if not repetidos:
        return []

    return list(
        Producto.objects
        .filter(id__in=set(repetidos))
        .order_by("nombre")
        .values_list("nombre", flat=True)
    )


def _agrupar_requeridos_por_almacen(lineas_stock):
    requeridos = {}
    for linea in lineas_stock:
        almacen_id = linea["almacen"].id
        producto_id = linea["producto"].id
        requeridos.setdefault(almacen_id, {})
        requeridos[almacen_id][producto_id] = (
            requeridos[almacen_id].get(producto_id, Decimal("0")) + linea["cantidad"]
        )
    return requeridos


def _primer_almacen_de_item(lineas_stock, item_index):
    for linea in lineas_stock:
        if linea.get("item_index") == item_index:
            return linea["almacen"]
    return lineas_stock[0]["almacen"] if lineas_stock else None


def _guardar_productos_agregados_a_nota(*, salida, detalles_validos, detalles_meta, lineas_stock, request):
    detalles_por_index = {}

    for index, detalle in enumerate(detalles_validos):
        meta = detalles_meta[index] if index < len(detalles_meta) else {}
        detalle.salida = salida
        detalle.almacen = _primer_almacen_de_item(lineas_stock, index) or salida.almacen

        producto = getattr(detalle, "producto", None)
        detalle.costo_unitario_aplicado = (
            getattr(producto, "costo_promedio", Decimal("0")) if producto else Decimal("0")
        )
        detalle.presentacion_nombre = meta.get("presentacion_nombre") or "Kilos"
        detalle.presentacion_conversion_id = meta.get("presentacion_id") or "default"
        cantidad_presentacion = meta.get("cantidad_presentacion")
        detalle.cantidad_presentacion = (
            cantidad_presentacion
            if cantidad_presentacion is not None
            else detalle.cantidad
        )
        detalle.presentacion_factor_conversion = meta.get("factor_conversion") or Decimal("1")
        detalle.presentacion_metrica_default = meta.get("metrica_default") or "kg"
        detalle.presentacion_equivalencia_texto = (
            meta.get("equivalencia_texto")
            or f"1 {detalle.presentacion_nombre} = {detalle.presentacion_factor_conversion} {detalle.presentacion_metrica_default}"
        )
        detalle.save()
        detalles_por_index[index] = detalle

    for linea in lineas_stock:
        detalle = detalles_por_index.get(linea.get("item_index"))
        if not detalle:
            continue
        SalidaInventarioDetalleAlmacen.objects.create(
            detalle=detalle,
            almacen=linea["almacen"],
            cantidad=linea["cantidad"],
        )

    for almacen_id, requeridos in _agrupar_requeridos_por_almacen(lineas_stock).items():
        aplicar_movimientos_salida(almacen_id=almacen_id, requeridos=requeridos)

    cliente = getattr(salida, "cliente_ref", None)
    for detalle in detalles_por_index.values():
        registrar_ultimo_precio_cliente(
            cliente=cliente,
            producto=detalle.producto,
            precio=detalle.precio_unitario,
            usuario=request.user if request and request.user.is_authenticated else None,
            observaciones=f"Producto agregado en edición de venta {salida.folio}",
        )

    return list(detalles_por_index.values())


@permiso_requerido("inventarios.change_salidainventario")
@transaction.atomic
def editar_nota_venta(request, pk):
    """
    Permite editar datos administrativos/precios y agregar nuevos productos.
    Los productos ya existentes no cambian producto, cantidad, presentación ni almacén.
    Los productos nuevos usan el mismo parser/validación de stock de la captura de venta.
    """
    salida = get_object_or_404(
        SalidaInventario.objects.select_for_update().prefetch_related(
            Prefetch(
                "detalles",
                queryset=SalidaInventarioDetalle.objects.select_related("producto", "almacen").order_by("id"),
            )
        ),
        pk=pk,
        tipo=SalidaInventario.TIPO_VENTA,
    )

    if salida.estado == SalidaInventario.ESTADO_CANCELADA:
        messages.error(request, "No se puede editar una nota cancelada.")
        return redirect("ventas_list")

    contexto_venta = get_contexto_salida_venta()
    almacenes_permitidos = {
        str(almacen.id): almacen
        for almacen in contexto_venta["almacenes_qs"]
    }

    DetallePrecioFormSet = modelformset_factory(
        SalidaInventarioDetalle,
        form=SalidaVentaDetallePrecioForm,
        extra=0,
        can_delete=False,
    )
    NuevoProductoFormSet = modelformset_factory(
        SalidaInventarioDetalle,
        form=SalidaInventarioDetalleForm,
        extra=0,
        can_delete=True,
    )

    detalles_qs = salida.detalles.all().annotate(importe=_importe_expr()).order_by("id")

    if request.method == "POST":
        form = SalidaVentaEdicionForm(request.POST, instance=salida)
        formset = DetallePrecioFormSet(request.POST, queryset=detalles_qs, prefix="precios")
        nuevos_formset = NuevoProductoFormSet(
            request.POST,
            queryset=SalidaInventarioDetalle.objects.none(),
            prefix="nuevos",
        )

        base_valida = form.is_valid() and formset.is_valid() and nuevos_formset.is_valid()
        hay_nuevos = _hay_productos_nuevos_en_post(request, prefix="nuevos")
        resultado_parseo = {"detalles_validos": [], "detalles_meta": [], "lineas_stock": [], "errores": []}

        if base_valida and hay_nuevos:
            productos_repetidos = _productos_nuevos_repetidos_en_nota(
                request=request,
                salida=salida,
                prefix="nuevos",
            )
            if productos_repetidos:
                messages.error(
                    request,
                    "No se pueden agregar productos que ya existen en la nota: "
                    + ", ".join(productos_repetidos)
                    + "."
                )
                base_valida = False

        if base_valida and hay_nuevos:
            parser = VentaPostParser(
                request=request,
                formset=nuevos_formset,
                almacenes_permitidos=almacenes_permitidos,
            )
            resultado_parseo = parser.parse()
            for error in resultado_parseo["errores"]:
                messages.error(request, error)
            base_valida = not resultado_parseo["errores"]

        if base_valida and hay_nuevos:
            venta_service = VentaService(
                form=form,
                detalles_validos=resultado_parseo["detalles_validos"],
                detalles_meta=resultado_parseo["detalles_meta"],
                lineas_stock=resultado_parseo["lineas_stock"],
                almacenes_permitidos=almacenes_permitidos,
                request=request,
            )
            errores_stock = venta_service.validar_stock()
            for error in errores_stock:
                messages.error(request, error)
            base_valida = not errores_stock

        if base_valida:
            salida_editada = form.save(commit=False)
            salida_editada.editada_en = timezone.now()
            salida_editada.editada_por = request.user if request.user.is_authenticated else None
            salida_editada.save()
            formset.save()

            if hay_nuevos:
                _guardar_productos_agregados_a_nota(
                    salida=salida_editada,
                    detalles_validos=resultado_parseo["detalles_validos"],
                    detalles_meta=resultado_parseo["detalles_meta"],
                    lineas_stock=resultado_parseo["lineas_stock"],
                    request=request,
                )

            msg_extra = " y se agregaron productos" if hay_nuevos else ""
            messages.success(request, f"Nota {salida.folio} editada correctamente{msg_extra}.")
            return redirect("ventas_list")

        messages.error(request, "Revisa los datos capturados. La nota no fue editada.")
    else:
        form = SalidaVentaEdicionForm(instance=salida)
        formset = DetallePrecioFormSet(queryset=detalles_qs, prefix="precios")
        nuevos_formset = NuevoProductoFormSet(
            queryset=SalidaInventarioDetalle.objects.none(),
            prefix="nuevos",
        )

    return render(request, "inventarios/nota_venta_edit.html", {
        "salida": salida,
        "form": form,
        "formset": formset,
        "nuevos_formset": nuevos_formset,
        "detalles": detalles_qs,
        "clientes": Cliente.objects.filter(activo=True).order_by("nombre_fiscal", "nombre_comercial"),
        "productos_ui": contexto_venta["productos_ui"],
        "productos_existentes_ids": list(salida.detalles.values_list("producto_id", flat=True)),
        "almacenes": contexto_venta["almacenes_qs"],
    })

@permiso_requerido("inventarios.view_salidainventario")
def nota_venta_print(request, pk=None):
    """
    Formato imprimible para una o varias notas.
    Uso:
      /inventarios/ventas/notas/12/imprimir/
      /inventarios/ventas/notas/imprimir/?ids=12,13,14
    """
    if pk:
        ids = [pk]
    else:
        raw_ids = (request.GET.get("ids") or "").strip()
        ids = [int(x) for x in raw_ids.split(",") if x.strip().isdigit()]

    notas = (
        SalidaInventario.objects
        .filter(id__in=ids, tipo=SalidaInventario.TIPO_VENTA)
        .select_related("almacen", "cliente_ref")
        .annotate(
            total_cantidad=Sum("detalles__cantidad"),
            total_importe=Sum(_importe_detalles_expr()),
        )
        .prefetch_related(
            Prefetch(
                "detalles",
                queryset=SalidaInventarioDetalle.objects
                    .select_related("producto", "almacen")
                    .prefetch_related("asignaciones__almacen")
                    .annotate(importe=_importe_expr())
                    .order_by("id"),
            )
        )
        .order_by("folio")
    )

    return render(request, "inventarios/nota_venta_print.html", {
        "notas": notas,
        "impreso_en": timezone.localtime(),
    })


@permiso_requerido("inventarios.change_salidainventario")
@transaction.atomic
@require_POST
def cancelar_nota_venta(request, pk):
    salida = get_object_or_404(
        SalidaInventario.objects.select_for_update().prefetch_related(
            "detalles__asignaciones__almacen",
            "detalles__producto",
        ),
        pk=pk,
        tipo=SalidaInventario.TIPO_VENTA,
    )

    if salida.estado == SalidaInventario.ESTADO_CANCELADA:
        messages.warning(request, f"La nota {salida.folio} ya se encontraba cancelada.")
        return redirect("ventas_list")

    motivo = (request.POST.get("motivo_cancelacion") or "").strip()
    if not motivo:
        messages.error(request, "Captura el motivo de cancelación.")
        return redirect("ventas_list")

    retornos = {}
    for detalle in salida.detalles.all():
        asignaciones = list(detalle.asignaciones.all())
        if asignaciones:
            for asignacion in asignaciones:
                retornos[(detalle.producto_id, asignacion.almacen_id)] = (
                    retornos.get((detalle.producto_id, asignacion.almacen_id), Decimal("0")) + asignacion.cantidad
                )
        else:
            almacen_id = detalle.almacen_id or salida.almacen_id
            if not almacen_id:
                raise ValueError(
                    f"No se puede cancelar la nota {salida.folio}: el detalle {detalle.id} no tiene almacén asociado."
                )
            retornos[(detalle.producto_id, almacen_id)] = (
                retornos.get((detalle.producto_id, almacen_id), Decimal("0")) + detalle.cantidad
            )

    for (producto_id, almacen_id), cantidad in retornos.items():
        aplicar_movimiento_stock(producto_id=producto_id, almacen_id=almacen_id, delta=cantidad)

    salida.estado = SalidaInventario.ESTADO_CANCELADA
    salida.cancelada_en = timezone.now()
    salida.motivo_cancelacion = motivo
    salida.save(update_fields=["estado", "cancelada_en", "motivo_cancelacion"])

    messages.success(request, f"Nota {salida.folio} cancelada. El inventario fue retornado correctamente.")
    return redirect("ventas_list")
