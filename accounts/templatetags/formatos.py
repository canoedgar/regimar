from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import template
from django.contrib.humanize.templatetags.humanize import intcomma

register = template.Library()


def _to_decimal(value):
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def redondear_entero(value):
    """Regla comercial: .49 hacia abajo y .50 hacia arriba."""
    return _to_decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


@register.filter
def precio_entero(value):
    """Muestra precios unitarios sin decimales y con separador de miles."""
    return intcomma(redondear_entero(value))


@register.filter
def dinero_decimal(value):
    """Muestra importes, subtotales y totales con 2 decimales y separador de miles."""
    return intcomma(_to_decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


@register.filter
def dinero_entero(value):
    """Muestra precio unitario completo: $ 1,234."""
    return f"$ {precio_entero(value)}"


@register.filter
def precio_entero_input(value):
    """Valor entero sin separadores para inputs type=number."""
    return str(redondear_entero(value))


@register.filter
def cantidad_decimal(value):
    """Muestra cantidades/stock con 2 decimales."""
    return intcomma(_to_decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
