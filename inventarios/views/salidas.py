from catalogos.models import Almacen, Producto, ClienteProductoPrecio, ParametroSistema, PrecioMenorMinimoAutorizacion
from ..models import SalidaInventario, SalidaInventarioDetalle
from ..forms import (
    SalidaInventarioDetalleForm,
    SalidaVentaForm,
    SalidaProyectoForm,
)
from django.db.models import F, Sum, ExpressionWrapper, DecimalField, Prefetch
from django.db.models.functions import Round
from django.db import transaction
from django.contrib import messages
from ..utils import get_almacen_default
from ..services.stock import (
    agrupar_requeridos_por_producto,
    validar_stock_suficiente,
    errores_stock_humano,
    aplicar_movimientos_salida,
)
from ..services.folios import next_folio_movimiento
from ..services.venta_parser import VentaPostParser
from ..services.ventas import VentaService
from ..selectors.ventas import get_contexto_salida_venta
from django.forms import modelformset_factory
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from catalogos.sat_catalogos import REGIMEN_FISCAL_CHOICES
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth.decorators import user_passes_test, login_required
from accounts.decorators import administrador_requerido, grupos_requeridos, permiso_requerido
from catalogos.services.clientes_precios import registrar_ultimo_precio_cliente


def _es_admin(user):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name="Administrador").exists())


@permiso_requerido("catalogos.view_clienteproductoprecio")
def precios_cliente_api(request):
    cliente_id = (request.GET.get("cliente_id") or "").strip()
    producto_ids = request.GET.getlist("producto_id")
    if not cliente_id:
        return JsonResponse({"precios": {}, "vigencia_dias": ParametroSistema.get_int("PRECIO_VIGENCIA_DIAS", 0)})

    precios = ClienteProductoPrecio.objects.filter(cliente_id=cliente_id)
    if producto_ids:
        precios = precios.filter(producto_id__in=[pid for pid in producto_ids if str(pid).isdigit()])

    data = {}
    for precio in precios.select_related("producto"):
        data[str(precio.producto_id)] = {
            "precio": float(precio.ultimo_precio or 0),
            "fecha": precio.fecha_ultimo_precio.isoformat() if precio.fecha_ultimo_precio else "",
            "dias_sin_compra": precio.dias_sin_compra,
            "vigente": precio.vigente,
        }
    return JsonResponse({"precios": data, "vigencia_dias": ParametroSistema.get_int("PRECIO_VIGENCIA_DIAS", 0)})


@permiso_requerido("catalogos.change_preciomenorminimoautorizacion")
def autorizar_precio_minimo(request, token):
    autorizacion = get_object_or_404(PrecioMenorMinimoAutorizacion.objects.select_related("cliente", "producto"), token=token)
    if not autorizacion.puede_usarse():
        messages.error(request, "La autorización ya fue usada o expiró.")
        return redirect("home")

    registrar_ultimo_precio_cliente(
        cliente=autorizacion.cliente,
        producto=autorizacion.producto,
        precio=autorizacion.precio_solicitado,
        usuario=request.user,
        observaciones="Autorización de precio menor al mínimo",
    )
    autorizacion.usado_en = timezone.now()
    autorizacion.autorizado_por = request.user
    autorizacion.save(update_fields=["usado_en", "autorizado_por"])
    messages.success(
        request,
        f"Precio autorizado para {autorizacion.cliente} / {autorizacion.producto}: ${autorizacion.precio_solicitado}.",
    )
    return redirect("precios_clientes_list")


def _importe_salida_expr(prefix=""):
    """
    Regla única para importes de salida:
    cantidad es la métrica base que afecta inventario; precio_unitario es precio por esa métrica base.
    cantidad_presentacion solo se usa para mostrar la captura original.
    """
    cantidad = f"{prefix}cantidad"
    precio = f"{prefix}precio_unitario"
    return ExpressionWrapper(
        F(cantidad) * F(precio),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )


def _get_nota_guardada_para_impresion(pk):
    """
    Recarga la nota recién guardada con los mismos importes que usan ventas_list y nota_venta_print.
    Evita que salida_venta_form muestre $0 o un total calculado con presentación.
    """
    return (
        SalidaInventario.objects
        .filter(pk=pk, tipo=SalidaInventario.TIPO_VENTA)
        .select_related("almacen", "cliente_ref", "almacen_origen", "almacen_destino", "registrado_por")
        .annotate(
            total_cantidad=Sum("detalles__cantidad"),
            total_importe=Sum(_importe_salida_expr("detalles__")),
        )
        .prefetch_related(
            Prefetch(
                "detalles",
                queryset=(
                    SalidaInventarioDetalle.objects
                    .select_related("producto", "almacen")
                    .prefetch_related("asignaciones__almacen")
                    .annotate(importe=_importe_salida_expr())
                    .order_by("id")
                ),
            )
        )
        .get()
    )


@permiso_requerido("inventarios.view_salidainventario")
def salidas_list(request):
    almacenes_qs = Almacen.objects.filter(es_activo=True).order_by("tipo", "nombre")
    almacen_id = (request.GET.get("almacen") or "").strip()

    salidas = (
        SalidaInventario.objects
        .select_related("almacen", "cliente_ref", "almacen_origen", "almacen_destino", "registrado_por")
        .all()
        .prefetch_related("detalles")
        .annotate(
            total_productos=Sum("detalles__cantidad"),
            total_importe=Round(
                Sum(_importe_salida_expr("detalles__")),
                2,
            ),
        )
    )

    tipo = request.GET.get("tipo")
    tipos_validos = dict(SalidaInventario.TIPO_CHOICES)

    if tipo in tipos_validos:
        salidas = salidas.filter(tipo=tipo)

    if almacen_id.isdigit():
        salidas = salidas.filter(almacen_id=int(almacen_id))

    context = {
        "salidas": salidas,
        "tipo_actual": tipo,
        "almacenes": almacenes_qs,
        "almacen_id": almacen_id,
        "TIPO_CHOICES": SalidaInventario.TIPO_CHOICES,
    }

    return render(request, "inventarios/salidas_list.html", context)


@permiso_requerido("inventarios.view_salidainventario")
def salida_detalle(request, pk):
    salida = get_object_or_404(
        SalidaInventario.objects
        .select_related("almacen", "proyecto", "cliente_ref", "almacen_origen", "almacen_destino", "registrado_por")
        .prefetch_related("detalles__producto"),
        pk=pk,
    )

    detalles = (
        salida.detalles.all()
        .select_related("producto")
        .annotate(
            importe=_importe_salida_expr()
        )
    )

    totales = detalles.aggregate(
        total_productos=Sum("cantidad"),
        total_importe=Sum("importe"),
    )

    return render(request, "inventarios/salida_detalle.html", {
        "salida": salida,
        "detalles": detalles,
        "total_productos": totales["total_productos"] or 0,
        "total_importe": totales["total_importe"] or 0,
    })


def _get_detalle_formset_factory(can_delete=True):
    return modelformset_factory(
        SalidaInventarioDetalle,
        form=SalidaInventarioDetalleForm,
        extra=0,
        can_delete=can_delete,
    )


def _get_form_venta_inicial():
    return SalidaVentaForm(initial={
        "folio": next_folio_movimiento(tipo="VTA", width=6),
        "fecha": timezone.localdate(),
        "forma_pago_venta": "",
        "estado_pago": SalidaInventario.ESTADO_PAGO_PENDIENTE,
    })


def _render_salida_venta_form(
    request,
    form,
    formset,
    productos_ui,
    clientes,
    almacenes_qs,
    almacen_default,
    nota_guardada=None,
):
    context = {
        "form": form,
        "formset": formset,
        "productos_ui": productos_ui,
        "clientes": clientes,
        "almacenes": almacenes_qs,
        "almacen": almacen_default,
        "REGIMEN_FISCAL_CHOICES": REGIMEN_FISCAL_CHOICES,
    }

    if nota_guardada is not None:
        context["nota_guardada"] = nota_guardada

    return render(request, "inventarios/salida_venta_form.html", context)


def _render_salida_venta_desde_contexto(
    request,
    form,
    formset,
    contexto_venta,
    nota_guardada=None,
):
    return _render_salida_venta_form(
        request=request,
        form=form,
        formset=formset,
        productos_ui=contexto_venta["productos_ui"],
        clientes=contexto_venta["clientes"],
        almacenes_qs=contexto_venta["almacenes_qs"],
        almacen_default=contexto_venta["almacen_default"],
        nota_guardada=nota_guardada,
    )


@permiso_requerido("inventarios.add_salidainventario")
@transaction.atomic
def salida_venta_create(request):
    DetalleFormSet = _get_detalle_formset_factory(can_delete=True)
    contexto_venta = get_contexto_salida_venta()

    almacen_default = contexto_venta["almacen_default"]

    if not almacen_default:
        messages.error(
            request,
            "No hay almacenes activos. Crea al menos uno para operar inventario.",
        )
        return redirect("almacenes_create")

    if request.method == "POST":
        form = SalidaVentaForm(request.POST)
        formset = DetalleFormSet(
            request.POST,
            queryset=SalidaInventarioDetalle.objects.none(),
        )

        if not form.is_valid() or not formset.is_valid():
            messages.error(request, "Revisa los datos. Hay campos inválidos.")

            return _render_salida_venta_desde_contexto(
                request=request,
                form=form,
                formset=formset,
                contexto_venta=contexto_venta,
            )

        almacenes_permitidos = {
            str(almacen.id): almacen
            for almacen in contexto_venta["almacenes_qs"]
        }

        parser = VentaPostParser(
            request=request,
            formset=formset,
            almacenes_permitidos=almacenes_permitidos,
        )

        resultado_parseo = parser.parse()
        errores_parseo = resultado_parseo["errores"]

        if errores_parseo:
            for error in errores_parseo:
                messages.error(request, error)

            return _render_salida_venta_desde_contexto(
                request=request,
                form=form,
                formset=formset,
                contexto_venta=contexto_venta,
            )

        venta_service = VentaService(
            form=form,
            detalles_validos=resultado_parseo["detalles_validos"],
            detalles_meta=resultado_parseo["detalles_meta"],
            lineas_stock=resultado_parseo["lineas_stock"],
            almacenes_permitidos=almacenes_permitidos,
            request=request,
        )

        errores_stock = venta_service.validar_stock()

        if errores_stock:
            for error in errores_stock:
                messages.error(request, error)

            return _render_salida_venta_desde_contexto(
                request=request,
                form=form,
                formset=formset,
                contexto_venta=contexto_venta,
            )

        salida = venta_service.guardar()

        messages.success(
            request,
            "Venta guardada correctamente. Ya puedes imprimir la nota generada.",
        )

        contexto_actualizado = get_contexto_salida_venta()

        nota_guardada = _get_nota_guardada_para_impresion(salida.pk)

        return _render_salida_venta_desde_contexto(
            request=request,
            form=_get_form_venta_inicial(),
            formset=DetalleFormSet(
                queryset=SalidaInventarioDetalle.objects.none()
            ),
            contexto_venta=contexto_actualizado,
            nota_guardada=nota_guardada,
        )

    form = _get_form_venta_inicial()
    formset = DetalleFormSet(queryset=SalidaInventarioDetalle.objects.none())

    return _render_salida_venta_desde_contexto(
        request=request,
        form=form,
        formset=formset,
        contexto_venta=contexto_venta,
    )

    almacenes_qs = Almacen.objects.filter(es_activo=True).order_by("tipo", "nombre")

    almacen_default = get_almacen_default()
    almacen = almacen_default or almacenes_qs.first()

    if not almacen:
        messages.error(request, "No hay almacenes activos.")
        return redirect("almacenes_create")

    DetalleFormSet = _get_detalle_formset_factory(can_delete=False)

    if request.method == "POST":
        almacen_id = (request.POST.get("almacen_id") or "").strip()

        if almacen_id.isdigit():
            almacen = almacenes_qs.filter(id=int(almacen_id)).first() or almacen

        form = SalidaProyectoForm(request.POST)
        formset = DetalleFormSet(
            request.POST,
            queryset=SalidaInventarioDetalle.objects.none(),
        )

        if not form.is_valid() or not formset.is_valid():
            messages.error(request, "Revisa los datos capturados.")

            return render(request, "inventarios/salida_proyecto_form.html", {
                "form": form,
                "formset": formset,
                "almacenes": almacenes_qs,
                "almacen": almacen,
            })

        detalles_validos = []

        for detalle_form in formset:
            cleaned_data = getattr(detalle_form, "cleaned_data", None)

            if not cleaned_data:
                continue

            producto = cleaned_data.get("producto")
            cantidad = cleaned_data.get("cantidad") or 0
            precio = cleaned_data.get("precio_unitario")

            if producto and cantidad > 0:
                detalles_validos.append({
                    "producto": producto,
                    "cantidad": cantidad,
                    "precio": precio,
                })

        if not detalles_validos:
            messages.error(
                request,
                "Agrega al menos un producto con cantidad mayor a 0.",
            )

            return render(request, "inventarios/salida_proyecto_form.html", {
                "form": form,
                "formset": formset,
                "almacenes": almacenes_qs,
                "almacen": almacen,
            })

        productos_vistos = set()
        productos_duplicados = set()

        for detalle in detalles_validos:
            producto_id = detalle["producto"].id

            if producto_id in productos_vistos:
                productos_duplicados.add(detalle["producto"])

            productos_vistos.add(producto_id)

        if productos_duplicados:
            messages.error(
                request,
                "No puedes repetir productos en el detalle: "
                + ", ".join([str(producto) for producto in productos_duplicados]),
            )

            return render(request, "inventarios/salida_proyecto_form.html", {
                "form": form,
                "formset": formset,
                "almacenes": almacenes_qs,
                "almacen": almacen,
            })

        requeridos = agrupar_requeridos_por_producto(
            (detalle["producto"].id, detalle["cantidad"])
            for detalle in detalles_validos
        )

        productos_por_id = {
            producto.id: str(producto)
            for producto in Producto.objects.filter(id__in=requeridos.keys())
        }

        ok, disponibles, faltantes = validar_stock_suficiente(
            almacen_id=almacen.id,
            requeridos=requeridos,
        )

        if not ok:
            for msg in errores_stock_humano(
                almacen_nombre=str(almacen),
                faltantes=faltantes,
                disponibles=disponibles,
                productos_por_id=productos_por_id,
            ):
                messages.error(request, msg)

            return render(request, "inventarios/salida_proyecto_form.html", {
                "form": form,
                "formset": formset,
                "almacenes": almacenes_qs,
                "almacen": almacen,
            })

        salida = form.save(commit=False)
        salida.almacen = almacen
        salida.save()

        for detalle in detalles_validos:
            SalidaInventarioDetalle.objects.create(
                salida=salida,
                producto=detalle["producto"],
                cantidad=detalle["cantidad"],
                precio_unitario=detalle["precio"],
            )

        aplicar_movimientos_salida(
            almacen_id=almacen.id,
            requeridos=requeridos,
        )

        messages.success(request, "Salida por proyecto registrada correctamente.")
        return redirect("salidas_list")

    form = SalidaProyectoForm(initial={
        "folio": next_folio_movimiento(tipo="PRY", width=6),
        "fecha": timezone.localdate(),
    })

    formset = DetalleFormSet(queryset=SalidaInventarioDetalle.objects.none())

    return render(request, "inventarios/salida_proyecto_form.html", {
        "form": form,
        "formset": formset,
        "almacenes": almacenes_qs,
        "almacen": almacen,
    })
