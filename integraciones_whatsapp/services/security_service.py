"""Validaciones de seguridad para la integración WhatsApp."""

from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any

from django.conf import settings
from django.db.models import Q

from integraciones_whatsapp.models import WhatsAppRemitenteAutorizado

_SIGNATURE_PREFIX = "sha256="


def is_webhook_enabled() -> bool:
    """Indica si el webhook de WhatsApp está habilitado por configuración."""
    return bool(getattr(settings, "WHATSAPP_WEBHOOK_ENABLED", False))


def validate_verify_token(mode: str | None, verify_token: str | None) -> bool:
    """Valida el token recibido en el GET de verificación de Meta.

    No se registran tokens en logs para evitar exposición de credenciales.
    """
    expected_token = getattr(settings, "WHATSAPP_VERIFY_TOKEN", "")

    return (
        is_webhook_enabled()
        and mode == "subscribe"
        and bool(expected_token)
        and verify_token == expected_token
    )


def should_validate_signature() -> bool:
    """Indica si debe validarse x-hub-signature-256.

    La validación se activa cuando WHATSAPP_APP_SECRET está configurado.
    """
    return bool(getattr(settings, "WHATSAPP_APP_SECRET", ""))


def validate_meta_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Valida la firma x-hub-signature-256 enviada por Meta.

    Meta envía el encabezado en formato:
        x-hub-signature-256: sha256=<hash>

    Si WHATSAPP_APP_SECRET no está configurado, la función regresa False para
    evitar asumir que un payload es confiable cuando se usa explícitamente.
    """
    app_secret = getattr(settings, "WHATSAPP_APP_SECRET", "")
    if not app_secret or not signature_header:
        return False

    signature_header = signature_header.strip()
    if not signature_header.startswith(_SIGNATURE_PREFIX):
        return False

    expected = _SIGNATURE_PREFIX + hmac.new(
        app_secret.encode("utf-8"),
        raw_body or b"",
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature_header)


def normalize_phone(phone: str | None) -> str:
    """Normaliza teléfonos al formato internacional con signo +.

    Reglas iniciales:
    - Conserva solo dígitos.
    - Si son 10 dígitos, antepone WHATSAPP_DEFAULT_COUNTRY_CODE.
    - Devuelve +<dígitos>.
    """
    digits = re.sub(r"\D+", "", str(phone or ""))
    if not digits:
        return ""

    default_country_code = str(getattr(settings, "WHATSAPP_DEFAULT_COUNTRY_CODE", "52") or "").strip()
    default_country_code = re.sub(r"\D+", "", default_country_code)

    if default_country_code and len(digits) == 10:
        digits = f"{default_country_code}{digits}"

    return f"+{digits}"


def phone_lookup_variants(phone: str | None) -> list[str]:
    """Devuelve variantes razonables para buscar un teléfono guardado."""
    normalized = normalize_phone(phone)
    digits = re.sub(r"\D+", "", str(phone or ""))

    variants = []
    for value in (str(phone or "").strip(), normalized, normalized.lstrip("+"), digits):
        if value and value not in variants:
            variants.append(value)

    return variants


def get_authorized_sender(phone: str | None) -> WhatsAppRemitenteAutorizado | None:
    """Busca un remitente autorizado por teléfono."""
    variants = phone_lookup_variants(phone)
    if not variants:
        return None

    return (
        WhatsAppRemitenteAutorizado.objects.filter(Q(telefono__in=variants))
        .select_related("usuario_sistema")
        .first()
    )


def is_sender_active(phone: str | None) -> bool:
    """Valida que el teléfono exista como remitente autorizado activo."""
    sender = get_authorized_sender(phone)
    return bool(sender and sender.activo)


def validate_authorized_sender(phone: str | None) -> tuple[bool, WhatsAppRemitenteAutorizado | None]:
    """Regresa si el remitente existe y está activo junto con el registro."""
    sender = get_authorized_sender(phone)
    return bool(sender and sender.activo), sender


def sender_has_permission(sender: WhatsAppRemitenteAutorizado | None, permission_field: str) -> bool:
    """Valida permisos booleanos definidos en WhatsAppRemitenteAutorizado."""
    if not sender or not sender.activo:
        return False
    return bool(getattr(sender, permission_field, False))


def get_request_signature(headers: Any) -> str:
    """Obtiene la firma desde headers compatibles con Django request.headers."""
    if not headers:
        return ""
    return headers.get("x-hub-signature-256") or headers.get("X-Hub-Signature-256") or ""
