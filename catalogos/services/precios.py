from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.utils import timezone

from catalogos.models import ProductoPrecioBitacora, ProductoPrecioHistorial


def _to_decimal(value, default="0"):
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _q2(value):
    return _to_decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _q4(value):
    return _to_decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calcular_margen(precio_venta, costo_promedio):
    precio_venta = _to_decimal(precio_venta)
    costo_promedio = _to_decimal(costo_promedio)
    margen = precio_venta - costo_promedio
    margen_porcentaje = Decimal("0")
    if precio_venta > 0:
        margen_porcentaje = (margen / precio_venta) * Decimal("100")
    return _q4(margen), _q2(margen_porcentaje)


def registrar_bitacora_precio_producto(producto, usuario=None, motivo=""):
    """
    Crea o actualiza la fotografía diaria del producto.
    Mantiene solo un registro por producto y fecha.
    """
    margen, margen_porcentaje = calcular_margen(
        producto.precio,
        producto.costo_promedio,
    )

    bitacora, _ = ProductoPrecioBitacora.objects.update_or_create(
        producto=producto,
        fecha=timezone.localdate(),
        defaults={
            "precio_venta": _q2(producto.precio),
            "precio_minimo": _q2(producto.precio_minimo),
            "ultimo_costo_compra": _q4(producto.ultimo_costo_compra),
            "costo_promedio": _q4(producto.costo_promedio),
            "stock_actual": _q4(producto.stock),
            "margen_estimado": margen,
            "margen_porcentaje": margen_porcentaje,
            "usuario": usuario if getattr(usuario, "is_authenticated", False) else None,
            "motivo": motivo or "Actualización de panorama de precios",
        },
    )
    return bitacora


def registrar_historial_precio_producto(
    *,
    producto,
    precio_anterior,
    precio_nuevo,
    precio_minimo_anterior,
    precio_minimo_nuevo,
    usuario=None,
    motivo="",
):
    precio_anterior = _q2(precio_anterior)
    precio_nuevo = _q2(precio_nuevo)
    precio_minimo_anterior = _q2(precio_minimo_anterior)
    precio_minimo_nuevo = _q2(precio_minimo_nuevo)

    if precio_anterior == precio_nuevo and precio_minimo_anterior == precio_minimo_nuevo:
        return None

    return ProductoPrecioHistorial.objects.create(
        producto=producto,
        precio_anterior=precio_anterior,
        precio_nuevo=precio_nuevo,
        precio_minimo_anterior=precio_minimo_anterior,
        precio_minimo_nuevo=precio_minimo_nuevo,
        usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
        motivo=motivo or "Cambio manual de precio",
    )
