from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone


class VentaPrecioMinimoNotificacionService:
    """Notificaciones del flujo de autorización por precio menor al mínimo."""

    @staticmethod
    def obtener_correos_administradores():
        User = get_user_model()
        admins = User.objects.filter(is_active=True).filter(is_superuser=True)
        return [usuario.email for usuario in admins if usuario.email]

    def enviar_solicitud(self, *, autorizacion, contexto=None):
        correos = self.obtener_correos_administradores()
        if not correos:
            return False

        url = self._build_url_autorizacion(autorizacion=autorizacion, contexto=contexto)
        usuario = contexto.username() if contexto is not None else "Sistema"
        producto = autorizacion.producto
        cliente = autorizacion.cliente

        asunto = f"Autorización de precio menor al mínimo - {producto.nombre}"
        cuerpo = (
            f"Cliente: {cliente}\n"
            f"Producto: {producto.nombre}\n"
            f"Precio actual/sugerido: ${autorizacion.precio_actual}\n"
            f"Precio mínimo: ${autorizacion.precio_minimo}\n"
            f"Precio solicitado: ${autorizacion.precio_solicitado}\n"
            f"Usuario: {usuario}\n"
            f"Fecha: {timezone.localtime().strftime('%Y-%m-%d %H:%M')}\n\n"
            f"Autorizar: {url}\n"
            "Este enlace es de un solo uso y expira en 24 horas."
        )

        send_mail(
            asunto,
            cuerpo,
            getattr(settings, "DEFAULT_FROM_EMAIL", None),
            correos,
            fail_silently=True,
        )
        return True

    def _build_url_autorizacion(self, *, autorizacion, contexto=None):
        path = reverse("autorizar_precio_minimo", kwargs={"token": autorizacion.token})
        if contexto is not None:
            return contexto.build_absolute_uri(path)
        return path
