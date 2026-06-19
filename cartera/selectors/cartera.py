from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from inventarios.models import SalidaInventario
from cartera.models import ClienteSaldoFavorMovimiento, PagoAplicacionNota, PagoCliente


MONEY_FIELD = DecimalField(max_digits=14, decimal_places=2)


def expresion_total_nota(prefix="detalles__"):
    """
    Importe de una nota de venta.

    Cuando se usa desde SalidaInventario se requiere el prefijo `detalles__`
    porque el cálculo cruza hacia SalidaInventarioDetalle.

    Cuando se usa directamente sobre `nota.detalles` el queryset ya está
    posicionado en SalidaInventarioDetalle, por lo que no debe llevar prefijo.
    """
    return ExpressionWrapper(
        F(f"{prefix}cantidad") * F(f"{prefix}precio_unitario"),
        output_field=MONEY_FIELD,
    )


def get_total_nota(nota: SalidaInventario) -> Decimal:
    return nota.detalles.aggregate(
        total=Coalesce(
            Sum(expresion_total_nota(prefix="")),
            Value(Decimal("0.00"), output_field=MONEY_FIELD),
        )
    )["total"]


def get_total_aplicado_pagos_nota(nota: SalidaInventario) -> Decimal:
    return PagoAplicacionNota.objects.filter(
        nota_venta=nota,
        pago__estado=PagoCliente.ESTADO_ACTIVO,
    ).aggregate(total=Coalesce(Sum("monto_aplicado"), Value(Decimal("0.00"), output_field=MONEY_FIELD)))["total"]


def get_total_saldo_favor_aplicado_nota(nota: SalidaInventario) -> Decimal:
    return ClienteSaldoFavorMovimiento.objects.filter(
        nota_aplicada=nota,
        tipo=ClienteSaldoFavorMovimiento.TIPO_APLICACION,
    ).aggregate(total=Coalesce(Sum("monto"), Value(Decimal("0.00"), output_field=MONEY_FIELD)))["total"]


def get_total_aplicado_nota(nota: SalidaInventario) -> Decimal:
    return get_total_aplicado_pagos_nota(nota) + get_total_saldo_favor_aplicado_nota(nota)


def get_saldo_pendiente_nota(nota: SalidaInventario) -> Decimal:
    saldo = get_total_nota(nota) - get_total_aplicado_nota(nota)
    return max(saldo, Decimal("0.00"))


def get_notas_venta_con_totales():
    aplicado_pagos_subquery = (
        PagoAplicacionNota.objects.filter(nota_venta=OuterRef("pk"), pago__estado=PagoCliente.ESTADO_ACTIVO)
        .values("nota_venta")
        .annotate(total=Sum("monto_aplicado"))
        .values("total")[:1]
    )
    aplicado_saldo_favor_subquery = (
        ClienteSaldoFavorMovimiento.objects.filter(
            nota_aplicada=OuterRef("pk"),
            tipo=ClienteSaldoFavorMovimiento.TIPO_APLICACION,
        )
        .values("nota_aplicada")
        .annotate(total=Sum("monto"))
        .values("total")[:1]
    )

    return (
        SalidaInventario.objects.filter(
            tipo=SalidaInventario.TIPO_VENTA,
            estado=SalidaInventario.ESTADO_ACTIVA,
            estado_pago__in=[
                SalidaInventario.ESTADO_PAGO_PENDIENTE,
                getattr(SalidaInventario, "ESTADO_PAGO_PARCIAL", "PARC"),
            ],
        )
        .select_related("cliente_ref")
        .annotate(
            total_nota=Coalesce(Sum(expresion_total_nota()), Value(Decimal("0.00"), output_field=MONEY_FIELD)),
            total_aplicado_pagos=Coalesce(Subquery(aplicado_pagos_subquery, output_field=MONEY_FIELD), Value(Decimal("0.00"), output_field=MONEY_FIELD)),
            total_aplicado_saldo_favor=Coalesce(Subquery(aplicado_saldo_favor_subquery, output_field=MONEY_FIELD), Value(Decimal("0.00"), output_field=MONEY_FIELD)),
        )
        .annotate(total_aplicado=ExpressionWrapper(F("total_aplicado_pagos") + F("total_aplicado_saldo_favor"), output_field=MONEY_FIELD))
        .annotate(saldo_pendiente=ExpressionWrapper(F("total_nota") - F("total_aplicado"), output_field=MONEY_FIELD))
    )


def get_notas_con_saldo_pendiente(cliente):
    return (
        get_notas_venta_con_totales()
        .filter(cliente_ref=cliente, saldo_pendiente__gt=0)
        .order_by("fecha", "folio", "id")
    )


def get_total_adeudado_cliente(cliente) -> Decimal:
    total = Decimal("0.00")
    for nota in get_notas_con_saldo_pendiente(cliente):
        total += nota.saldo_pendiente
    return total


def get_saldo_favor_cliente(cliente) -> Decimal:
    movimientos = ClienteSaldoFavorMovimiento.objects.filter(cliente=cliente)
    genera = movimientos.filter(tipo=ClienteSaldoFavorMovimiento.TIPO_GENERACION).aggregate(
        total=Coalesce(Sum("monto"), Value(Decimal("0.00"), output_field=MONEY_FIELD))
    )["total"]
    resta = movimientos.filter(
        tipo__in=[
            ClienteSaldoFavorMovimiento.TIPO_APLICACION,
            ClienteSaldoFavorMovimiento.TIPO_DEVOLUCION,
            ClienteSaldoFavorMovimiento.TIPO_CANCELACION,
        ]
    ).aggregate(total=Coalesce(Sum("monto"), Value(Decimal("0.00"), output_field=MONEY_FIELD)))["total"]
    return max(genera - resta, Decimal("0.00"))


def get_historial_pagos_cliente(cliente):
    return (
        PagoCliente.objects.filter(cliente=cliente)
        .prefetch_related("metodos", "aplicaciones__nota_venta")
        .order_by("-fecha", "-id")
    )


def get_estado_cuenta_cliente(cliente):
    return {
        "cliente": cliente,
        "total_adeudado": get_total_adeudado_cliente(cliente),
        "saldo_favor": get_saldo_favor_cliente(cliente),
        "notas_pendientes": get_notas_con_saldo_pendiente(cliente),
        "pagos": get_historial_pagos_cliente(cliente),
    }
