# inventarios/services/costos.py

from decimal import Decimal

from django.db.models import F
from django.utils import timezone

from catalogos.models import Producto

from ..models import InventarioStock
from ..utils import decimal_or_default as _to_decimal


def costo_virtual_producto(producto) -> Decimal:
    """
    Costo histórico usado para entradas automáticas de almacenes virtuales.
    Se prioriza el último costo de compra; si no existe, se usa costo promedio.
    """
    if not producto:
        return Decimal("0")
    return _to_decimal(
        getattr(producto, "ultimo_costo_compra", Decimal("0"))
        or getattr(producto, "costo_promedio", Decimal("0"))
        or Decimal("0")
    )


def costo_promedio_almacen(*, producto_id: int, almacen_id: int) -> Decimal:
    stock_row = InventarioStock.objects.filter(
        producto_id=producto_id,
        almacen_id=almacen_id,
    ).first()
    return _to_decimal(getattr(stock_row, "costo_promedio", 0) if stock_row else 0)


def recalcular_costo_promedio_producto(producto_id: int):
    """
    Recalcula el costo promedio general del producto usando los stocks por almacén.
    El promedio del producto se usa como referencia comercial y de margen.
    """
    rows = InventarioStock.objects.filter(producto_id=producto_id)

    cantidad_total = Decimal("0")
    valor_total = Decimal("0")

    for row in rows:
        cantidad = _to_decimal(row.cantidad)
        costo = _to_decimal(getattr(row, "costo_promedio", Decimal("0")))
        if cantidad > 0:
            cantidad_total += cantidad
            valor_total += cantidad * costo

    nuevo_promedio = Decimal("0")
    if cantidad_total > 0:
        nuevo_promedio = valor_total / cantidad_total

    Producto.objects.filter(pk=producto_id).update(costo_promedio=nuevo_promedio)
    return nuevo_promedio


def aplicar_entrada_con_costo(
    *,
    producto_id: int,
    almacen_id: int,
    cantidad,
    costo_unitario,
    actualizar_ultima_compra=True,
):
    """
    Suma inventario y recalcula costo promedio ponderado por almacén.

    Este servicio se encarga exclusivamente de la valorización del inventario:
    cantidad + costo promedio. La bitácora comercial se registra por separado.
    costo_unitario debe venir expresado en la métrica base del producto.
    """
    cantidad = _to_decimal(cantidad)
    costo_unitario = _to_decimal(costo_unitario)

    if cantidad <= 0:
        return

    stock_row, _ = InventarioStock.objects.select_for_update().get_or_create(
        producto_id=producto_id,
        almacen_id=almacen_id,
        defaults={"cantidad": Decimal("0"), "costo_promedio": Decimal("0")},
    )

    cantidad_actual = _to_decimal(stock_row.cantidad)
    costo_actual = _to_decimal(getattr(stock_row, "costo_promedio", Decimal("0")))

    valor_actual = cantidad_actual * costo_actual
    valor_entrada = cantidad * costo_unitario
    nueva_cantidad = cantidad_actual + cantidad

    nuevo_costo_promedio = Decimal("0")
    if nueva_cantidad > 0:
        nuevo_costo_promedio = (valor_actual + valor_entrada) / nueva_cantidad

    stock_row.cantidad = nueva_cantidad
    stock_row.costo_promedio = nuevo_costo_promedio
    stock_row.save(update_fields=["cantidad", "costo_promedio"])

    update_kwargs = {"stock": F("stock") + cantidad}
    if actualizar_ultima_compra:
        update_kwargs.update({
            "ultimo_costo_compra": costo_unitario,
            "fecha_ultima_compra": timezone.localdate(),
        })

    Producto.objects.filter(pk=producto_id).update(**update_kwargs)
    recalcular_costo_promedio_producto(producto_id)
