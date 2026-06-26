"""Cliente para comunicación saliente con Meta WhatsApp Cloud API."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from .security_service import normalize_phone

logger = logging.getLogger(__name__)


class MetaClientError(Exception):
    """Error controlado al comunicarse con Meta."""


class MetaClientConfigurationError(MetaClientError):
    """Error de configuración incompleta para consumir Meta."""


class MetaClientHTTPError(MetaClientError):
    """Error HTTP devuelto por Meta."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Meta respondió HTTP {status_code}: {detail}")


def send_text_message(to: str, message: str) -> dict[str, Any]:
    """Envía un mensaje de texto por WhatsApp Cloud API."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": _recipient_for_meta(to),
        "type": "text",
        "text": {
            "preview_url": False,
            "body": str(message or ""),
        },
    }
    return _post_messages(payload)


def send_template_message(to: str, template_name: str, language_code: str = "en_US") -> dict[str, Any]:
    """Envía un template aprobado por Meta."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": _recipient_for_meta(to),
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
        },
    }
    return _post_messages(payload)


def _post_messages(payload: dict[str, Any]) -> dict[str, Any]:
    access_token = getattr(settings, "WHATSAPP_ACCESS_TOKEN", "")
    phone_number_id = getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
    if not access_token or not phone_number_id:
        raise MetaClientConfigurationError(
            "Faltan WHATSAPP_ACCESS_TOKEN o WHATSAPP_PHONE_NUMBER_ID en la configuración."
        )

    url = _messages_endpoint(phone_number_id)
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    timeout = int(getattr(settings, "WHATSAPP_META_TIMEOUT", 20) or 20)

    try:
        with urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if not response_body:
                return {}
            return json.loads(response_body)
    except HTTPError as exc:
        detail = _safe_error_detail(exc)
        logger.warning("Meta WhatsApp API respondió con error HTTP %s: %s", exc.code, detail)
        raise MetaClientHTTPError(exc.code, detail) from exc
    except URLError as exc:
        logger.warning("No fue posible conectar con Meta WhatsApp API: %s", exc.reason)
        raise MetaClientError("No fue posible conectar con Meta WhatsApp API.") from exc
    except json.JSONDecodeError as exc:
        logger.warning("Meta WhatsApp API devolvió una respuesta JSON inválida.")
        raise MetaClientError("Meta devolvió una respuesta JSON inválida.") from exc


def _messages_endpoint(phone_number_id: str) -> str:
    api_version = getattr(settings, "WHATSAPP_GRAPH_API_VERSION", "v25.0") or "v25.0"
    return f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"


def _recipient_for_meta(phone: str) -> str:
    normalized = normalize_phone(phone)
    return normalized.lstrip("+")


def _safe_error_detail(exc: HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8")
    except Exception:
        return "error_sin_detalle"

    if not raw:
        return "error_sin_detalle"

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:500]

    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        message = error.get("message") or "error_sin_mensaje"
        code = error.get("code") or "sin_codigo"
        return f"code={code}; message={message}"

    return raw[:500]
