from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Prefetch, Sum, Value
from django.db.models.functions import Coalesce

from catalogos.models import Cliente, Producto
from inventarios.models import SalidaInventario, SalidaInventarioDetalle
from ventas.selectors.ventas import get_contexto_salida_venta
from ventas.services.comisiones import MONEY_FIELD, total_importe_con_comision_expr


def importe_detalle_expr():
    return ExpressionWrapper(
        F("cantidad") * F("precio_unitario"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )


def importe_salida_expr():
    return ExpressionWrapper(
        F("detalles__cantidad") * F("detalles__precio_unitario"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )


def detalles_nota_qs():
    return (
        SalidaInventarioDetalle.objects
        .select_related("producto", "almacen")
        .prefetch_related("asignaciones__almacen")
        .annotate(importe=importe_detalle_expr())
        .order_by("id")
    )


def get_nota_venta(pk, *, for_update=False):
    qs = SalidaInventario.objects
    if for_update:
        qs = qs.select_for_update()

    return (
        qs.filter(pk=pk, tipo=SalidaInventario.TIPO_VENTA)
        .select_related("almacen", "cliente_ref", "editada_por")
        .prefetch_related(Prefetch("detalles", queryset=detalles_nota_qs()))
        .annotate(
            total_cantidad=Sum("detalles__cantidad"),
            subtotal_importe=Coalesce(Sum(importe_salida_expr()), Value(Decimal("0.00"), output_field=MONEY_FIELD)),
        )
        .annotate(total_importe=total_importe_con_comision_expr())
        .get()
    )


def get_nota_venta_qs_for_404(pk, *, for_update=False):
    qs = SalidaInventario.objects
    if for_update:
        qs = qs.select_for_update()
    return (
        qs.filter(pk=pk, tipo=SalidaInventario.TIPO_VENTA)
        .select_related("almacen", "cliente_ref", "editada_por")
        .prefetch_related(Prefetch("detalles", queryset=detalles_nota_qs()))
        .annotate(
            total_cantidad=Sum("detalles__cantidad"),
            subtotal_importe=Coalesce(Sum(importe_salida_expr()), Value(Decimal("0.00"), output_field=MONEY_FIELD)),
        )
        .annotate(total_importe=total_importe_con_comision_expr())
    )


def get_clientes_activos():
    return Cliente.objects.filter(activo=True).order_by("nombre_fiscal", "nombre_comercial")


def get_productos_catalogo():
    return Producto.objects.all().order_by("nombre")


def get_contexto_agregar_productos(salida):
    contexto = get_contexto_salida_venta()
    productos_existentes_ids = list(salida.detalles.values_list("producto_id", flat=True))
    contexto["productos_existentes_ids"] = productos_existentes_ids
    return contexto
