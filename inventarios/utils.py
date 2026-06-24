# inventarios/utils.py

from decimal import Decimal, InvalidOperation

from catalogos.models import Almacen, Producto


def decimal_or_default(value, default="0"):
    """
    Convierte valores de formularios/modelos a Decimal de forma segura.

    Permite usar default=None cuando el consumidor necesita distinguir un
    valor inválido de cero.
    """
    if value in (None, ""):
        return default if default is None else Decimal(str(default))

    if isinstance(value, Decimal):
        return value

    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default if default is None else Decimal(str(default))


def decimal_text(value, default="0"):
    """Devuelve un Decimal como texto limpio, sin ceros decimales innecesarios."""
    value = decimal_or_default(value, default=default)
    if value is None:
        return ""

    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def get_almacen_default():
    return (
        Almacen.objects.filter(es_activo=True, tipo="FISICO").order_by("id").first()
        or Almacen.objects.filter(es_activo=True).order_by("id").first()
    )


def productos_con_conversiones_qs():
    """QuerySet base para pantallas que requieren conversiones por producto."""
    return (
        Producto.objects
        .prefetch_related("conversiones_metricas")
        .order_by("nombre")
    )


def build_productos_conversiones_json(productos, *, include_peso_variable=False):
    """
    Construye el JSON usado por las pantallas de captura que convierten
    presentaciones a la métrica base del producto.
    """
    data = {}
    for producto in productos:
        conversiones = []
        for conversion in producto.conversiones_metricas.all():
            if not conversion.activo:
                continue
            conversiones.append({
                "id": conversion.id,
                "nombre": conversion.nombre,
                "unidad_origen": conversion.unidad_origen,
                "cantidad_origen": decimal_text(conversion.cantidad_origen),
                "factor_conversion": decimal_text(conversion.factor_conversion),
                "texto": conversion.equivalencia_texto,
            })

        producto_data = {
            "id": producto.id,
            "nombre": producto.nombre,
            "metrica": producto.metrica or "kg",
            "conversiones": conversiones,
        }

        if include_peso_variable:
            producto_data["maneja_peso_variable"] = bool(
                getattr(producto, "maneja_peso_variable", False)
            )

        data[str(producto.id)] = producto_data

    return data
