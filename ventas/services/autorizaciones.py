"""Casos de uso para resolver autorizaciones comerciales de venta."""

from django.utils import timezone

from catalogos.models import ClienteCreditoAutorizacion, PrecioMenorMinimoAutorizacion
from catalogos.services.clientes_precios import registrar_ultimo_precio_cliente


def autorizar_precio_minimo_cliente(*, autorizacion, usuario):
    if not autorizacion.puede_usarse():
        return False, "La autorización ya fue usada o expiró."

    registrar_ultimo_precio_cliente(
        cliente=autorizacion.cliente,
        producto=autorizacion.producto,
        precio=autorizacion.precio_solicitado,
        usuario=usuario,
        observaciones="Autorización de precio menor al mínimo",
    )
    autorizacion.usado_en = timezone.now()
    autorizacion.autorizado_por = usuario
    autorizacion.save(update_fields=["usado_en", "autorizado_por"])
    return True, (
        f"Precio autorizado para {autorizacion.cliente} / {autorizacion.producto}: "
        f"${autorizacion.precio_solicitado}."
    )


def resolver_autorizacion_credito(*, autorizacion, accion, comentario="", es_post=False):
    mensaje = ""
    mensaje_tipo = "info"

    if es_post and autorizacion.puede_resolverse():
        accion = (accion or "").strip().lower()
        comentario = (comentario or "").strip()
        if accion == "autorizar":
            autorizacion.aprobar(comentario=comentario)
            mensaje = "Venta extraordinaria autorizada. El usuario ya puede continuar con el flujo de venta."
            mensaje_tipo = "success"
        elif accion == "rechazar":
            autorizacion.rechazar(comentario=comentario)
            mensaje = "Solicitud rechazada. El usuario no podrá usar esta autorización."
            mensaje_tipo = "danger"
        else:
            mensaje = "Acción inválida."
            mensaje_tipo = "warning"
    elif es_post:
        mensaje = "Este enlace ya fue usado, fue resuelto previamente o ya no corresponde al día de creación."
        mensaje_tipo = "warning"

    if not mensaje and not autorizacion.puede_resolverse():
        if not autorizacion.vigente_hoy:
            mensaje = "Este enlace ya expiró porque solo puede usarse el día de creación."
            mensaje_tipo = "warning"
        elif autorizacion.estado != ClienteCreditoAutorizacion.ESTADO_PENDIENTE:
            mensaje = "Esta solicitud ya fue resuelta previamente."
            mensaje_tipo = "info"

    return {
        "autorizacion": autorizacion,
        "puede_resolver": autorizacion.puede_resolverse(),
        "mensaje": mensaje,
        "mensaje_tipo": mensaje_tipo,
    }


def get_autorizacion_precio_queryset():
    return PrecioMenorMinimoAutorizacion.objects.select_related("cliente", "producto")


def get_autorizacion_credito_queryset():
    return ClienteCreditoAutorizacion.objects.select_related("cliente", "usuario_solicita")
