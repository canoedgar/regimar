import re

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from notificaciones.models import NotificacionCorreo

_DESTINATARIOS_SPLIT_RE = re.compile(r"[,;\n]+")


def normalizar_destinatarios(destinatarios):
    if isinstance(destinatarios, str):
        partes = _DESTINATARIOS_SPLIT_RE.split(destinatarios)
    else:
        partes = destinatarios or []
    return [correo.strip() for correo in partes if str(correo).strip()]


def enviar_correo(
    *,
    asunto,
    destinatarios,
    cuerpo_texto,
    cuerpo_html=None,
    tipo=NotificacionCorreo.TIPO_OTRO,
    usuario=None,
    metadata=None,
):
    """Envía un correo y registra la bitácora del envío.

    Esta función centraliza el envío para que otros módulos no dependan
    directamente de SMTP ni dupliquen trazabilidad.
    """
    destinatarios = normalizar_destinatarios(destinatarios)
    if not destinatarios:
        raise ValueError("No se capturaron destinatarios para enviar el correo.")

    registro = NotificacionCorreo.objects.create(
        tipo=tipo,
        asunto=asunto,
        destinatarios=", ".join(destinatarios),
        enviado_por=usuario if getattr(usuario, "is_authenticated", False) else None,
        metadata=metadata or {},
    )

    try:
        mensaje = EmailMultiAlternatives(
            subject=asunto,
            body=cuerpo_texto,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=destinatarios,
        )
        if cuerpo_html:
            mensaje.attach_alternative(cuerpo_html, "text/html")
        mensaje.send(fail_silently=False)
        registro.marcar_enviado()
        return registro
    except Exception as exc:
        registro.marcar_error(exc)
        raise
