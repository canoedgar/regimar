from catalogos.models import Almacen
from inventarios.models import SalidaInventario, SalidaInventarioDetalle
from django.db.models import F, Sum, ExpressionWrapper, DecimalField
from django.db.models.functions import Round
from django.shortcuts import render, get_object_or_404
from accounts.decorators import permiso_requerido


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
