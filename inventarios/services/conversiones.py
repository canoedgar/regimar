from decimal import Decimal

from catalogos.models import ProductoMetricaConversion

from ..utils import decimal_or_default as _to_decimal


def normalizar_captura_entrada(producto, cantidad_capturada, conversion_id_raw):
    """
    Normaliza una captura de entrada a la métrica base del producto.

    Se usa en casos de uso que reciben producto + cantidad + presentación,
    como ajustes positivos y entradas manuales sin peso variable.
    """
    metrica_base = getattr(producto, "metrica", None) or "kg"
    conversion = None
    conversion_id = None

    if str(conversion_id_raw or "").isdigit():
        conversion_id = int(conversion_id_raw)
        try:
            conversion = ProductoMetricaConversion.objects.get(
                id=conversion_id,
                producto_id=producto.pk,
                activo=True,
            )
        except ProductoMetricaConversion.DoesNotExist as exc:
            raise ValueError("La presentación seleccionada ya no es válida para ese producto.") from exc

    cantidad_base = _to_decimal(cantidad_capturada)
    presentacion_nombre = metrica_base
    equivalencia_texto = f"Base ({metrica_base})"
    factor_conversion = Decimal("1")
    presentacion_conversion_id = str(conversion_id or "default")

    if conversion:
        cantidad_base = conversion.convertir_a_default(cantidad_base)
        presentacion_nombre = conversion.unidad_origen or conversion.nombre
        equivalencia_texto = conversion.equivalencia_texto
        factor_conversion = conversion.factor_conversion

    if cantidad_base <= 0:
        raise ValueError("La cantidad convertida debe ser mayor a 0.")

    return {
        "cantidad_base": cantidad_base,
        "cantidad_presentacion": _to_decimal(cantidad_capturada),
        "presentacion_nombre": presentacion_nombre,
        "presentacion_conversion_id": presentacion_conversion_id,
        "presentacion_factor_conversion": factor_conversion,
        "presentacion_metrica_default": metrica_base,
        "presentacion_equivalencia_texto": equivalencia_texto,
        "conversion": conversion,
        "conversion_id": conversion_id,
    }
