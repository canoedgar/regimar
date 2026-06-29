from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce

from catalogos.models import ParametroSistema


PARAM_COMISION_TERMINAL = "COMISION_TERMINAL"
TWOPLACES = Decimal("0.01")
MONEY_FIELD = DecimalField(max_digits=14, decimal_places=2)


def money(value) -> Decimal:
    try:
        return Decimal(str(value or "0")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def percent(value) -> Decimal:
    try:
        return Decimal(str(value or "0").replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def get_porcentaje_comision_terminal(default=Decimal("0")) -> Decimal:
    parametro = ParametroSistema.objects.filter(clave__iexact=PARAM_COMISION_TERMINAL, activo=True).first()
    if not parametro:
        return percent(default)
    valor = percent(parametro.valor)
    return max(valor, Decimal("0"))


def es_forma_pago_terminal(forma_pago) -> bool:
    return str(forma_pago or "").upper() == "TERMINAL"


def es_nota_terminal(nota) -> bool:
    return es_forma_pago_terminal(getattr(nota, "forma_pago_venta", ""))


def calcular_monto_comision(subtotal, porcentaje) -> Decimal:
    subtotal = money(subtotal)
    porcentaje = percent(porcentaje)
    if subtotal <= 0 or porcentaje <= 0:
        return Decimal("0.00")
    return money(subtotal * porcentaje / Decimal("100"))


def calcular_total_con_comision(subtotal, *, forma_pago, porcentaje=None):
    subtotal = money(subtotal)
    porcentaje = get_porcentaje_comision_terminal() if porcentaje is None else percent(porcentaje)
    comision = calcular_monto_comision(subtotal, porcentaje) if es_forma_pago_terminal(forma_pago) else Decimal("0.00")
    return money(subtotal + comision)


def get_subtotal_nota(nota) -> Decimal:
    from cartera.selectors.cartera import expresion_total_nota

    return money(nota.detalles.aggregate(total=Coalesce(
        Sum(expresion_total_nota(prefix="")),
        Value(Decimal("0.00"), output_field=MONEY_FIELD),
    ))["total"])


def aplicar_comision_terminal(nota, *, subtotal=None, commit=True):
    """Calcula y persiste la comisión asociada a una nota pagada con terminal."""
    subtotal = money(get_subtotal_nota(nota) if subtotal is None else subtotal)

    if es_nota_terminal(nota):
        porcentaje = percent(getattr(nota, "comision_terminal_porcentaje", Decimal("0")))
        if porcentaje <= 0:
            porcentaje = get_porcentaje_comision_terminal()
        nota.comision_terminal_porcentaje = porcentaje
        nota.comision_terminal_monto = calcular_monto_comision(subtotal, porcentaje)
        nota.estado_pago = nota.ESTADO_PAGO_PAGADO
    else:
        nota.comision_terminal_porcentaje = Decimal("0")
        nota.comision_terminal_monto = Decimal("0.00")

    if commit:
        nota.save(update_fields=["comision_terminal_porcentaje", "comision_terminal_monto", "estado_pago"])
    return nota


def total_importe_con_comision_expr(subtotal_field="subtotal_importe"):
    return ExpressionWrapper(
        F(subtotal_field) + Coalesce(F("comision_terminal_monto"), Value(Decimal("0.00"), output_field=MONEY_FIELD)),
        output_field=MONEY_FIELD,
    )
