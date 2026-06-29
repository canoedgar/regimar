from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Prefetch, Q, Sum, Value
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import permiso_requerido
from catalogos.models import Almacen, Producto
from inventarios.models import SalidaInventario, SalidaInventarioDetalle
from ventas.services.cancelacion import CancelarNotaVentaService
from ventas.services.impresion import (
    get_contexto_impresion_notas,
    importe_detalles_expr,
    importe_linea_expr,
)
from ventas.services.comisiones import MONEY_FIELD, total_importe_con_comision_expr


def _importe_expr():
    return importe_linea_expr()


def _importe_detalles_expr():
    return importe_detalles_expr()


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


@permiso_requerido("ventas.view_notaventa")
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
        subtotal_importe=Coalesce(Sum(_importe_detalles_expr()), Value(Decimal("0.00"), output_field=MONEY_FIELD)),
        num_detalle_almacenes=Count("detalles__almacen", distinct=True),
        num_asignacion_almacenes=Count("detalles__asignaciones__almacen", distinct=True),
    ).annotate(total_importe=total_importe_con_comision_expr())

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
        subtotal_notas=Sum(_importe_expr()),
    )
    resumen_comisiones = SalidaInventario.objects.filter(
        id__in=ventas_activas_ids
    ).aggregate(
        total_comisiones=Sum("comision_terminal_monto"),
    )
    total_notas = (resumen["subtotal_notas"] or Decimal("0")) + (resumen_comisiones["total_comisiones"] or Decimal("0"))

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
        "total_notas": total_notas,
        "total_cantidad": resumen["total_cantidad"] or Decimal("0"),
    }
    return render(request, "ventas/ventas_list.html", context)



@permiso_requerido("ventas.view_notaventa")
def nota_venta_print(request, pk=None):
    """Formato imprimible para una o varias notas."""
    return render(
        request,
        "ventas/nota_venta_print.html",
        get_contexto_impresion_notas(
            pk=pk,
            raw_ids=(request.GET.get("ids") or "").strip(),
        ),
    )


@permiso_requerido("ventas.change_notaventa")
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

    service = CancelarNotaVentaService(
        salida=salida,
        motivo=request.POST.get("motivo_cancelacion"),
    )
    errores = service.validar()

    if salida.estado == SalidaInventario.ESTADO_CANCELADA:
        messages.warning(request, errores[0] if errores else f"La nota {salida.folio} ya se encontraba cancelada.")
        return redirect("ventas_list")

    if errores:
        for error in errores:
            messages.error(request, error)
        return redirect("ventas_list")

    service.execute()
    messages.success(request, f"Nota {salida.folio} cancelada. El inventario fue retornado correctamente.")
    return redirect("ventas_list")
