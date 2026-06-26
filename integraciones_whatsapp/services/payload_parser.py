"""Parser de payloads recibidos desde Meta WhatsApp Cloud API.

Convierte la estructura cruda enviada por Meta en estructuras internas simples
para que el webhook no contenga lógica de lectura del JSON.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ParsedWhatsAppMessage:
    """Representación interna mínima de un mensaje entrante."""

    message_id: str
    from_phone: str
    profile_name: str
    message_type: str
    text: str
    timestamp: str
    raw_message: dict[str, Any]
    raw_value: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Devuelve la estructura como dict para servicios que no usan dataclasses."""
        data = asdict(self)
        data["from"] = data.pop("from_phone")
        return data


class PayloadParserError(ValueError):
    """Error controlado de parseo de payload de WhatsApp."""


def is_meta_payload(payload: dict[str, Any]) -> bool:
    """Valida si el payload tiene la forma base enviada por Meta."""
    return payload.get("object") == "whatsapp_business_account" and isinstance(payload.get("entry"), list)


def extract_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extrae todos los mensajes entrantes del payload de Meta.

    Meta puede enviar varios entries, changes y messages en un mismo POST. Esta
    función los aplana en una lista simple y omite actualizaciones de estado.
    """
    if not payload:
        return []

    if not isinstance(payload, dict):
        raise PayloadParserError("El payload debe ser un diccionario.")

    if not is_meta_payload(payload):
        return []

    parsed_messages: list[dict[str, Any]] = []

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []) if isinstance(entry, dict) else []:
            value = change.get("value", {}) if isinstance(change, dict) else {}
            if not isinstance(value, dict):
                continue

            contacts_by_wa_id = _contacts_by_wa_id(value.get("contacts", []))

            for message in value.get("messages", []):
                if not isinstance(message, dict):
                    continue

                from_phone = str(message.get("from") or "").strip()
                contact = contacts_by_wa_id.get(from_phone, {})
                profile_name = _extract_profile_name(contact)
                message_type = str(message.get("type") or "unknown").strip() or "unknown"

                parsed = ParsedWhatsAppMessage(
                    message_id=str(message.get("id") or "").strip(),
                    from_phone=from_phone,
                    profile_name=profile_name,
                    message_type=message_type,
                    text=_extract_text(message, message_type),
                    timestamp=str(message.get("timestamp") or "").strip(),
                    raw_message=message,
                    raw_value=value,
                )
                parsed_messages.append(parsed.to_dict())

    return parsed_messages


def extract_first_message(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Devuelve el primer mensaje entrante encontrado o None."""
    messages = extract_messages(payload)
    return messages[0] if messages else None


def extract_status_updates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extrae actualizaciones de estado enviadas por Meta.

    Los status updates no deben convertirse en instrucciones operativas.
    """
    if not isinstance(payload, dict) or not is_meta_payload(payload):
        return []

    statuses: list[dict[str, Any]] = []

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []) if isinstance(entry, dict) else []:
            value = change.get("value", {}) if isinstance(change, dict) else {}
            if not isinstance(value, dict):
                continue
            for status in value.get("statuses", []):
                if isinstance(status, dict):
                    statuses.append(status)

    return statuses


def has_incoming_messages(payload: dict[str, Any]) -> bool:
    """Indica si el payload contiene mensajes entrantes."""
    return bool(extract_messages(payload))


def _contacts_by_wa_id(contacts: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(contacts, list):
        return result

    for contact in contacts:
        if not isinstance(contact, dict):
            continue
        wa_id = str(contact.get("wa_id") or "").strip()
        if wa_id:
            result[wa_id] = contact

    return result


def _extract_profile_name(contact: dict[str, Any]) -> str:
    profile = contact.get("profile", {}) if isinstance(contact, dict) else {}
    if not isinstance(profile, dict):
        return ""
    return str(profile.get("name") or "").strip()


def _extract_text(message: dict[str, Any], message_type: str) -> str:
    if message_type == "text":
        text = message.get("text", {})
        if isinstance(text, dict):
            return str(text.get("body") or "").strip()
        return ""

    if message_type == "button":
        button = message.get("button", {})
        if isinstance(button, dict):
            return str(button.get("text") or button.get("payload") or "").strip()
        return ""

    if message_type == "interactive":
        return _extract_interactive_text(message.get("interactive", {}))

    if message_type in {"image", "audio", "video", "document", "sticker"}:
        media = message.get(message_type, {})
        if isinstance(media, dict):
            return str(media.get("caption") or "").strip()

    if message_type == "location":
        location = message.get("location", {})
        if isinstance(location, dict):
            name = str(location.get("name") or "").strip()
            address = str(location.get("address") or "").strip()
            return " | ".join(part for part in (name, address) if part)

    return ""


def _extract_interactive_text(interactive: Any) -> str:
    if not isinstance(interactive, dict):
        return ""

    interactive_type = interactive.get("type")
    if interactive_type == "button_reply":
        button_reply = interactive.get("button_reply", {})
        if isinstance(button_reply, dict):
            return str(button_reply.get("title") or button_reply.get("id") or "").strip()

    if interactive_type == "list_reply":
        list_reply = interactive.get("list_reply", {})
        if isinstance(list_reply, dict):
            return str(list_reply.get("title") or list_reply.get("id") or "").strip()

    return ""
