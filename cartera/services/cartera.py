from datetime import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from inventarios.models import SalidaInventario
from cartera.models import ClienteSaldoFavorMovimiento, PagoAplicacionNota, PagoCliente, PagoMetodoDetalle
from cartera.selectors.cartera import get_saldo_favor_cliente, get_saldo_pendiente_nota, get_total_nota


TWOPLACES = Decimal("0.01")


def _money(value):
    return Decimal(value or 0).quantize(TWOPLACES)


def _normalizar_fecha_movimiento(fecha_movimiento=None):
    if not fecha_movimiento:
        return timezone.now()
    if isinstance(fecha_movimiento, datetime):
        return fecha_movimiento if timezone.is_aware(fecha_movimiento) else timezone.make_aware(fecha_movimiento)
    hora_registro = timezone.localtime().replace(microsecond=0).time().replace(tzinfo=None)
    fecha_hora = datetime.combine(fecha_movimiento, hora_registro)
    return timezone.make_aware(fecha_hora)


def _validar_metodos(monto_recibido, metodos):
    if not metodos:
        raise ValidationError("Captura al menos un método de pago.")
    total_metodos = sum((_money(m.get("monto")) for m in metodos), Decimal("0.00"))
    if total_metodos != _money(monto_recibido):
        raise ValidationError("La suma de métodos de pago debe coincidir con el monto recibido.")


def _crear_metodos_pago(pago, metodos):
    return [
        PagoMetodoDetalle.objects.create(
            pago=pago,
            metodo=metodo["metodo"],
            monto=_money(metodo["monto"]),
            referencia=metodo.get("referencia", ""),
        )
        for metodo in metodos
    ]


def actualizar_estado_pago_nota(nota):
    saldo = get_saldo_pendiente_nota(nota)
    total = get_total_nota(nota)
    aplicado = total - saldo

    if saldo <= 0:
        nuevo_estado = SalidaInventario.ESTADO_PAGO_PAGADO
    elif aplicado > 0:
        nuevo_estado = getattr(SalidaInventario, "ESTADO_PAGO_PARCIAL", "PARC")
    else:
        nuevo_estado = SalidaInventario.ESTADO_PAGO_PENDIENTE

    if nota.estado_pago != nuevo_estado:
        nota.estado_pago = nuevo_estado
        nota.save(update_fields=["estado_pago"])
    return nota.estado_pago


@transaction.atomic
def registrar_pago_automatico_nota_pagada(nota, usuario=None, metodo=PagoMetodoDetalle.METODO_EFECTIVO, fecha_pago=None):
    if nota.tipo != SalidaInventario.TIPO_VENTA:
        raise ValidationError("Solo se pueden registrar pagos automáticos de notas de venta.")
    if not nota.cliente_ref_id:
        raise ValidationError("La nota debe tener cliente de catálogo para registrar pago automático.")

    monto = _money(get_total_nota(nota))
    if monto <= 0:
        raise ValidationError("La nota no tiene importe para registrar pago.")

    pago = PagoCliente.objects.create(
        cliente=nota.cliente_ref,
        origen=PagoCliente.ORIGEN_AUTO_NOTA,
        tipo_aplicacion=PagoCliente.TIPO_AUTO,
        fecha=_normalizar_fecha_movimiento(fecha_pago),
        monto_recibido=monto,
        referencia=f"Pago automático nota {nota.folio}",
        creado_por=usuario,
    )
    PagoMetodoDetalle.objects.create(pago=pago, metodo=metodo, monto=monto)
    PagoAplicacionNota.objects.create(
        pago=pago,
        nota_venta=nota,
        monto_aplicado=monto,
        saldo_antes=monto,
        saldo_despues=Decimal("0.00"),
        creado_por=usuario,
    )
    actualizar_estado_pago_nota(nota)
    return pago


@transaction.atomic
def registrar_pago_notas_especificas(cliente, monto_recibido, aplicaciones, metodos, usuario=None, referencia="", observaciones="", fecha_pago=None):
    monto_recibido = _money(monto_recibido)
    if monto_recibido <= 0:
        raise ValidationError("El monto recibido debe ser mayor a cero.")
    _validar_metodos(monto_recibido, metodos)

    pago = PagoCliente.objects.create(
        cliente=cliente,
        tipo_aplicacion=PagoCliente.TIPO_DIRECTO,
        fecha=_normalizar_fecha_movimiento(fecha_pago),
        monto_recibido=monto_recibido,
        referencia=referencia,
        observaciones=observaciones,
        creado_por=usuario,
    )
    _crear_metodos_pago(pago, metodos)

    total_aplicado = Decimal("0.00")
    for item in aplicaciones:
        nota = SalidaInventario.objects.select_for_update().get(pk=item["nota_id"])
        if nota.cliente_ref_id != cliente.id:
            raise ValidationError("Todas las notas deben pertenecer al cliente seleccionado.")
        if nota.estado != SalidaInventario.ESTADO_ACTIVA:
            raise ValidationError(f"La nota {nota.folio} no está activa.")

        monto_aplicar = _money(item["monto"])
        saldo = _money(get_saldo_pendiente_nota(nota))
        if monto_aplicar <= 0:
            raise ValidationError("El monto a aplicar por nota debe ser mayor a cero.")
        if monto_aplicar > saldo:
            monto_aplicar = saldo
        if monto_aplicar <= 0:
            continue

        PagoAplicacionNota.objects.create(
            pago=pago,
            nota_venta=nota,
            monto_aplicado=monto_aplicar,
            saldo_antes=saldo,
            saldo_despues=max(saldo - monto_aplicar, Decimal("0.00")),
            creado_por=usuario,
        )
        total_aplicado += monto_aplicar
        actualizar_estado_pago_nota(nota)

    excedente = monto_recibido - total_aplicado
    if excedente > 0:
        ClienteSaldoFavorMovimiento.objects.create(
            cliente=cliente,
            tipo=ClienteSaldoFavorMovimiento.TIPO_GENERACION,
            monto=excedente,
            pago_origen=pago,
            fecha=pago.fecha,
            creado_por=usuario,
            observaciones="Excedente de pago aplicado a notas específicas.",
        )
    return pago


@transaction.atomic
def registrar_pago_fifo(cliente, monto_recibido, metodos, usuario=None, referencia="", observaciones="", fecha_pago=None):
    monto_recibido = _money(monto_recibido)
    if monto_recibido <= 0:
        raise ValidationError("El monto recibido debe ser mayor a cero.")
    _validar_metodos(monto_recibido, metodos)

    pago = PagoCliente.objects.create(
        cliente=cliente,
        tipo_aplicacion=PagoCliente.TIPO_FIFO,
        fecha=_normalizar_fecha_movimiento(fecha_pago),
        monto_recibido=monto_recibido,
        referencia=referencia,
        observaciones=observaciones,
        creado_por=usuario,
    )
    _crear_metodos_pago(pago, metodos)

    restante = monto_recibido
    notas = (
        SalidaInventario.objects.select_for_update()
        .filter(
            tipo=SalidaInventario.TIPO_VENTA,
            estado=SalidaInventario.ESTADO_ACTIVA,
            cliente_ref=cliente,
            estado_pago__in=[
                SalidaInventario.ESTADO_PAGO_PENDIENTE,
                getattr(SalidaInventario, "ESTADO_PAGO_PARCIAL", "PARC"),
            ],
        )
        .order_by("fecha", "folio", "id")
    )

    for nota in notas:
        if restante <= 0:
            break
        saldo = _money(get_saldo_pendiente_nota(nota))
        if saldo <= 0:
            actualizar_estado_pago_nota(nota)
            continue
        monto_aplicar = min(restante, saldo)
        PagoAplicacionNota.objects.create(
            pago=pago,
            nota_venta=nota,
            monto_aplicado=monto_aplicar,
            saldo_antes=saldo,
            saldo_despues=max(saldo - monto_aplicar, Decimal("0.00")),
            creado_por=usuario,
        )
        restante -= monto_aplicar
        actualizar_estado_pago_nota(nota)

    if restante > 0:
        ClienteSaldoFavorMovimiento.objects.create(
            cliente=cliente,
            tipo=ClienteSaldoFavorMovimiento.TIPO_GENERACION,
            monto=restante,
            pago_origen=pago,
            fecha=pago.fecha,
            creado_por=usuario,
            observaciones="Excedente de pago global aplicado automáticamente.",
        )
    return pago


@transaction.atomic
def devolver_saldo_favor(cliente, monto, metodo, usuario_autoriza, usuario_registra=None, referencia="", observaciones="", fecha_liquidacion=None):
    monto = _money(monto)
    if monto <= 0:
        raise ValidationError("El monto a devolver debe ser mayor a cero.")
    disponible = _money(get_saldo_favor_cliente(cliente))
    if monto > disponible:
        raise ValidationError("No se puede devolver un monto mayor al saldo a favor disponible.")

    return ClienteSaldoFavorMovimiento.objects.create(
        cliente=cliente,
        tipo=ClienteSaldoFavorMovimiento.TIPO_DEVOLUCION,
        monto=monto,
        metodo_devolucion=metodo,
        referencia=referencia,
        observaciones=observaciones,
        autorizado_por=usuario_autoriza,
        creado_por=usuario_registra or usuario_autoriza,
        fecha=_normalizar_fecha_movimiento(fecha_liquidacion),
    )


@transaction.atomic
def aplicar_saldo_favor_a_nota(cliente, nota, monto, usuario=None, referencia="", observaciones="", fecha_aplicacion=None):
    monto = _money(monto)
    if monto <= 0:
        raise ValidationError("El monto a aplicar debe ser mayor a cero.")
    if nota.tipo != SalidaInventario.TIPO_VENTA:
        raise ValidationError("Solo se puede aplicar saldo a favor a notas de venta.")
    if nota.estado != SalidaInventario.ESTADO_ACTIVA:
        raise ValidationError("Solo se puede aplicar saldo a favor a notas activas.")
    if nota.cliente_ref_id != cliente.id:
        raise ValidationError("La nota no pertenece al cliente seleccionado.")

    nota = SalidaInventario.objects.select_for_update().get(pk=nota.pk)
    saldo_disponible = _money(get_saldo_favor_cliente(cliente))
    if saldo_disponible <= 0:
        raise ValidationError("El cliente no tiene saldo a favor disponible.")
    if monto > saldo_disponible:
        raise ValidationError("No se puede aplicar un monto mayor al saldo a favor disponible.")

    saldo_nota = _money(get_saldo_pendiente_nota(nota))
    if saldo_nota <= 0:
        raise ValidationError("La nota seleccionada no tiene saldo pendiente.")
    if monto > saldo_nota:
        raise ValidationError("No se puede aplicar un monto mayor al saldo pendiente de la nota.")

    movimiento = ClienteSaldoFavorMovimiento.objects.create(
        cliente=cliente,
        tipo=ClienteSaldoFavorMovimiento.TIPO_APLICACION,
        monto=monto,
        nota_aplicada=nota,
        fecha=_normalizar_fecha_movimiento(fecha_aplicacion),
        creado_por=usuario,
        referencia=referencia,
        observaciones=observaciones,
    )
    actualizar_estado_pago_nota(nota)
    return movimiento
