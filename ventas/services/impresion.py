"""Servicios y expresiones para impresión/listados comerciales de notas de venta."""

from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Prefetch, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from inventarios.models import SalidaInventario, SalidaInventarioDetalle
from ventas.services.comisiones import MONEY_FIELD, total_importe_con_comision_expr


def importe_linea_expr(prefix=""):
    """
    Importe comercial de una línea de venta.

    Regla única del módulo:
    - cantidad = cantidad ya convertida a la métrica base que afecta inventario.
    - precio_unitario = precio por la métrica base.
    - cantidad_presentacion solo sirve para mostrar la captura original.
    """
    cantidad = f"{prefix}cantidad"
    precio = f"{prefix}precio_unitario"
    return ExpressionWrapper(
        F(cantidad) * F(precio),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )


def importe_detalles_expr():
    """Misma regla anterior, aplicada desde SalidaInventario hacia sus detalles."""
    return importe_linea_expr("detalles__")


def parse_nota_ids(*, pk=None, raw_ids=""):
    if pk:
        return [pk]
    return [int(value) for value in (raw_ids or "").split(",") if value.strip().isdigit()]


def get_nota_guardada_para_impresion(pk):
    """
    Recarga la nota recién guardada con los mismos importes que usan listados e impresión.
    Evita mostrar totales en cero o calculados con presentación.
    """
    return (
        SalidaInventario.objects
        .filter(pk=pk, tipo=SalidaInventario.TIPO_VENTA)
        .select_related("almacen", "cliente_ref", "almacen_origen", "almacen_destino", "registrado_por")
        .annotate(
            total_cantidad=Sum("detalles__cantidad"),
            subtotal_importe=Coalesce(Sum(importe_detalles_expr()), Value(Decimal("0.00"), output_field=MONEY_FIELD)),
        )
        .annotate(total_importe=total_importe_con_comision_expr())
        .prefetch_related(
            Prefetch(
                "detalles",
                queryset=(
                    SalidaInventarioDetalle.objects
                    .select_related("producto", "almacen")
                    .prefetch_related("asignaciones__almacen")
                    .annotate(importe=importe_linea_expr())
                    .order_by("id")
                ),
            )
        )
        .get()
    )


def get_notas_para_impresion(ids):
    return (
        SalidaInventario.objects
        .filter(id__in=ids, tipo=SalidaInventario.TIPO_VENTA)
        .select_related("almacen", "cliente_ref")
        .annotate(
            total_cantidad=Sum("detalles__cantidad"),
            subtotal_importe=Coalesce(Sum(importe_detalles_expr()), Value(Decimal("0.00"), output_field=MONEY_FIELD)),
        )
        .annotate(total_importe=total_importe_con_comision_expr())
        .prefetch_related(
            Prefetch(
                "detalles",
                queryset=(
                    SalidaInventarioDetalle.objects
                    .select_related("producto", "almacen")
                    .prefetch_related("asignaciones__almacen")
                    .annotate(importe=importe_linea_expr())
                    .order_by("id")
                ),
            )
        )
        .order_by("folio")
    )


def get_contexto_impresion_notas(*, pk=None, raw_ids=""):
    ids = parse_nota_ids(pk=pk, raw_ids=raw_ids)
    return {
        "notas": get_notas_para_impresion(ids),
        "impreso_en": timezone.localtime(),
    }
