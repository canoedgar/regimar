from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.decorators.http import require_POST

from catalogos.models import Almacen, Producto
from ..models import SalidaInventario, SalidaInventarioDetalle
from ..services.stock import aplicar_movimiento_stock


def _importe_expr():
    return ExpressionWrapper(
        Coalesce(F("cantidad_presentacion"), F("cantidad")) * F("precio_unitario"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )


def _importe_detalles_expr():
    return ExpressionWrapper(
        Coalesce(F("detalles__cantidad_presentacion"), F("detalles__cantidad")) * F("detalles__precio_unitario"),
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
        .select_related("almacen")
        .order_by("-fecha", "-folio")
    )

    folio = (request.GET.get("folio") or "").strip()
    cliente = (request.GET.get("cliente") or "").strip()
    fecha_inicio = (request.GET.get("fecha_inicio") or "").strip()
    fecha_fin = (request.GET.get("fecha_fin") or "").strip()
    estado = (request.GET.get("estado") or "").strip()
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
    )

    # Guardamos los IDs de las ventas filtradas antes de paginar
    ventas_ids = list(ventas.values_list("id", flat=True))

    resumen = SalidaInventarioDetalle.objects.filter(
        salida_id__in=ventas_ids
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

    querystring = request.GET.copy()
    querystring.pop("page", None)

    context = {
        "page_obj": page_obj,
        "ventas": page_obj.object_list,
        "productos": Producto.objects.all().order_by("nombre"),
        "almacenes": Almacen.objects.filter(es_activo=True).order_by("tipo", "nombre"),
        "estado_choices": SalidaInventario.ESTADO_CHOICES,
        "filtros": request.GET,
        "querystring": querystring.urlencode(),
        "total_notas": resumen["total_notas"] or Decimal("0"),
        "total_cantidad": resumen["total_cantidad"] or Decimal("0"),
    }
    return render(request, "inventarios/ventas_list.html", context)


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
        .select_related("almacen")
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