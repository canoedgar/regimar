import hashlib

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.utils import timezone


class SessionSecurityMiddleware:
    """
    Endurece la sesión de usuarios autenticados.

    Controles aplicados:
    - Caducidad por inactividad real.
    - Caducidad absoluta de la sesión.
    - Validación opcional de User-Agent e IP para reducir reutilización de cookies robadas.
    - Renovación de expiración de sesión en cada request válida.
    """

    STARTED_AT_KEY = "_security_started_at"
    LAST_ACTIVITY_KEY = "_security_last_activity"
    USER_AGENT_KEY = "_security_user_agent_hash"
    IP_KEY = "_security_ip_hash"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.process_request(request)
        if response is not None:
            return response
        return self.get_response(request)

    def process_request(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None

        now = int(timezone.now().timestamp())
        session = request.session

        started_at = session.get(self.STARTED_AT_KEY)
        last_activity = session.get(self.LAST_ACTIVITY_KEY)

        if started_at is None:
            session[self.STARTED_AT_KEY] = now
            started_at = now

        absolute_timeout = int(getattr(settings, "SESSION_ABSOLUTE_TIMEOUT", 0) or 0)
        if absolute_timeout > 0 and now - int(started_at) > absolute_timeout:
            return self._logout(request, "Tu sesión expiró por tiempo máximo permitido. Inicia sesión nuevamente.")

        idle_timeout = int(getattr(settings, "SESSION_IDLE_TIMEOUT", 0) or 0)
        if idle_timeout > 0 and last_activity is not None and now - int(last_activity) > idle_timeout:
            return self._logout(request, "Tu sesión expiró por inactividad. Inicia sesión nuevamente.")

        if getattr(settings, "SESSION_BIND_USER_AGENT", True):
            current_user_agent = self._hash(self._get_user_agent(request))
            stored_user_agent = session.get(self.USER_AGENT_KEY)
            if stored_user_agent and stored_user_agent != current_user_agent:
                return self._logout(request, "La sesión fue invalidada por cambio de navegador o dispositivo.")
            session[self.USER_AGENT_KEY] = current_user_agent

        if getattr(settings, "SESSION_BIND_IP", False):
            current_ip = self._hash(self._get_client_ip(request))
            stored_ip = session.get(self.IP_KEY)
            if stored_ip and stored_ip != current_ip:
                return self._logout(request, "La sesión fue invalidada por cambio de origen de conexión.")
            session[self.IP_KEY] = current_ip

        session[self.LAST_ACTIVITY_KEY] = now
        if idle_timeout > 0:
            session.set_expiry(idle_timeout)

        return None

    def _logout(self, request, message):
        logout(request)
        messages.warning(request, message)
        return redirect(settings.LOGIN_URL)

    def _get_user_agent(self, request):
        return request.META.get("HTTP_USER_AGENT", "")[:500]

    def _get_client_ip(self, request):
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")

    def _hash(self, value):
        return hashlib.sha256((value or "").encode("utf-8")).hexdigest()
