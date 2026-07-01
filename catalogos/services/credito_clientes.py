from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from cartera.selectors.cartera import (
    get_notas_con_saldo_pendiente,
    get_saldo_pendiente_nota,
    get_total_adeudado_cliente,
)
from catalogos.models import ClienteCreditoAutorizacion, ParametroSistema
from notificaciones.models import NotificacionCorreo
from notificaciones.services.correo import enviar_correo, normalizar_destinatarios

TWOPLACES = Decimal("0.01")


def money(value):
    return Decimal(value or 0).quantize(TWOPLACES)


def total_detalles_venta(detalles):
    total = Decimal("0.00")
    for detalle in detalles or []:
        total += money(getattr(detalle, "cantidad", 0)) * money(getattr(detalle, "precio_unitario", 0))
    return money(total)


def cliente_tiene_parametros_credito(cliente):
    if not cliente:
        return False
    limite = money(getattr(cliente, "limite_credito", 0))
    dias = int(getattr(cliente, "dias_credito", 0) or 0)
    return limite > 0 or dias > 0


def _get_correo_autorizacion():
    parametro = ParametroSistema.objects.filter(clave__iexact="CORREO_AUTORIZACION", activo=True).first()
    destinatarios = normalizar_destinatarios(parametro.valor if parametro else "")
    if not destinatarios:
        raise ValidationError(
            "No está configurado el parámetro de sistema CORREO_AUTORIZACION para solicitar autorizaciones de cartera."
        )
    return destinatarios


def _saldo_actual_para_validacion(cliente, venta_existente=None):
    saldo = money(get_total_adeudado_cliente(cliente))
    if venta_existente is not None and getattr(venta_existente, "pk", None):
        try:
            saldo -= money(get_saldo_pendiente_nota(venta_existente))
        except Exception:
            pass
    return max(money(saldo), Decimal("0.00"))


def _notas_vencidas(cliente, dias_credito, venta_existente=None):
    if dias_credito <= 0:
        return []
    fecha_limite = timezone.localdate() - timedelta(days=dias_credito)
    qs = get_notas_con_saldo_pendiente(cliente).filter(fecha__lt=fecha_limite)
    if venta_existente is not None and getattr(venta_existente, "pk", None):
        qs = qs.exclude(pk=venta_existente.pk)
    return list(qs[:5])


def _construir_bloqueos(cliente, total_venta, fecha_venta, venta_existente=None):
    limite_credito = money(getattr(cliente, "limite_credito", 0))
    dias_credito = int(getattr(cliente, "dias_credito", 0) or 0)
    saldo_actual = _saldo_actual_para_validacion(cliente, venta_existente=venta_existente)
    saldo_proyectado = money(saldo_actual + money(total_venta))
    bloqueos = []

    if limite_credito > 0 and saldo_proyectado > limite_credito:
        bloqueos.append(
            "Límite de crédito excedido: "
            f"saldo actual ${saldo_actual}, venta ${money(total_venta)}, "
            f"saldo proyectado ${saldo_proyectado}, límite ${limite_credito}."
        )

    if dias_credito > 0:
        vencidas = _notas_vencidas(cliente, dias_credito, venta_existente=venta_existente)
        if vencidas:
            folios = ", ".join(nota.folio for nota in vencidas)
            bloqueos.append(
                f"El cliente tiene notas vencidas con más de {dias_credito} días de crédito: {folios}."
            )

        if fecha_venta and fecha_venta + timedelta(days=dias_credito) < timezone.localdate():
            bloqueos.append(
                f"La fecha de venta {fecha_venta:%Y-%m-%d} ya rebasa los {dias_credito} días de crédito configurados."
            )

    return bloqueos, saldo_actual, saldo_proyectado, limite_credito, dias_credito


def _solicitud_hoy(cliente):
    return (
        ClienteCreditoAutorizacion.objects
        .filter(cliente=cliente, fecha_solicitud=timezone.localdate())
        .order_by("-creado_en", "-id")
        .first()
    )


def _enviar_correo_solicitud(request, autorizacion):
    destinatarios = _get_correo_autorizacion()
    url = request.build_absolute_uri(
        reverse("autorizar_venta_extraordinaria", kwargs={"token": autorizacion.token})
    )
    usuario = (
        request.user.get_username()
        if request and getattr(request, "user", None) and request.user.is_authenticated
        else "Sistema"
    )
    contexto = {
        "autorizacion": autorizacion,
        "url_autorizacion": url,
        "usuario": usuario,
        "fecha": timezone.localtime(),
    }
    asunto = f"Autorización de venta extraordinaria - {autorizacion.cliente}"
    cuerpo_texto = render_to_string("catalogos/emails/autorizacion_credito.txt", contexto)
    cuerpo_html = render_to_string("catalogos/emails/autorizacion_credito.html", contexto)
    enviar_correo(
        asunto=asunto,
        destinatarios=destinatarios,
        cuerpo_texto=cuerpo_texto,
        cuerpo_html=cuerpo_html,
        tipo=NotificacionCorreo.TIPO_OTRO,
        usuario=request.user if request and getattr(request, "user", None) else None,
        metadata={
            "tipo": "AUTORIZACION_CREDITO_CLIENTE",
            "autorizacion_id": autorizacion.id,
            "cliente_id": autorizacion.cliente_id,
        },
    )


@transaction.atomic
def validar_credito_cliente_para_venta(*, cliente, total_venta, fecha_venta=None, request=None, venta_existente=None):
    """Valida parámetros de crédito y administra la solicitud diaria de autorización.

    Retorna (errores, autorizacion_aprobada_disponible). Si no hay errores y
    existe autorización aprobada, la vista/servicio debe marcarla como usada
    después de guardar correctamente la venta.
    """
    if not cliente_tiene_parametros_credito(cliente):
        return [], None

    total_venta = money(total_venta)
    fecha_venta = fecha_venta or timezone.localdate()
    bloqueos, saldo_actual, saldo_proyectado, limite_credito, dias_credito = _construir_bloqueos(
        cliente,
        total_venta,
        fecha_venta,
        venta_existente=venta_existente,
    )

    if not bloqueos:
        return [], None

    solicitud = _solicitud_hoy(cliente)
    if solicitud:
        if solicitud.disponible_para_venta:
            if total_venta <= money(solicitud.total_venta) and saldo_proyectado <= money(solicitud.saldo_proyectado):
                return [], solicitud
            return [
                "La autorización de cartera aprobada para hoy no cubre el importe actual de la venta. "
                f"Autorizado: ${solicitud.total_venta}; venta actual: ${total_venta}."
            ], None
        if solicitud.estado == ClienteCreditoAutorizacion.ESTADO_PENDIENTE:
            return [
                "La venta requiere autorización de cartera. Ya existe una solicitud en proceso para este cliente el día de hoy."
            ], None
        if solicitud.estado == ClienteCreditoAutorizacion.ESTADO_APROBADA and solicitud.usado_en is not None:
            return [
                "La autorización de cartera de hoy ya fue utilizada. No se puede reutilizar para otra venta extraordinaria."
            ], None
        if solicitud.estado == ClienteCreditoAutorizacion.ESTADO_RECHAZADA:
            return ["La solicitud de autorización de cartera de hoy fue rechazada."], None

    if request is None:
        return ["La venta requiere autorización de cartera, pero no fue posible generar la solicitud sin contexto de solicitud web."], None

    motivo = "\n".join(bloqueos)
    autorizacion = ClienteCreditoAutorizacion.objects.create(
        cliente=cliente,
        usuario_solicita=request.user if request.user.is_authenticated else None,
        total_venta=total_venta,
        saldo_actual=saldo_actual,
        saldo_proyectado=saldo_proyectado,
        limite_credito=limite_credito,
        dias_credito=dias_credito,
        motivo=motivo,
    )
    try:
        _enviar_correo_solicitud(request, autorizacion)
    except Exception as exc:
        autorizacion.delete()
        return [f"La venta requiere autorización de cartera, pero no se pudo enviar el correo: {exc}"], None

    return [
        "La venta requiere autorización de cartera. Se envió la solicitud al correo configurado de Regimar."
    ], None


@transaction.atomic
def marcar_autorizacion_credito_usada(autorizacion, venta):
    if not autorizacion:
        return None
    autorizacion = ClienteCreditoAutorizacion.objects.select_for_update().get(pk=autorizacion.pk)
    if not autorizacion.disponible_para_venta:
        raise ValidationError("La autorización de cartera ya no está disponible para usarse.")
    autorizacion.marcar_usada(venta=venta)
    return autorizacion
