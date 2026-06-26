"""Servicio orquestador del webhook de WhatsApp."""

from __future__ import annotations

import json
import logging
from typing import Any

from django.db import DatabaseError

from .instruction_service import (
    crear_instruccion_desde_payload,
    registrar_error,
    registrar_error_desde_raw_payload,
)
from .payload_parser import extract_messages, extract_status_updates, is_meta_payload

logger = logging.getLogger(__name__)


class WebhookPayloadError(ValueError):
    """Error controlado para payloads que no pueden convertirse a JSON."""


def decode_payload(raw_body: bytes) -> dict[str, Any]:
    """Convierte el body recibido por Meta en un diccionario Python."""
    if not raw_body:
        return {}

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise WebhookPayloadError("El payload no está codificado como UTF-8.") from exc
    except json.JSONDecodeError as exc:
        raise WebhookPayloadError("El payload no contiene JSON válido.") from exc

    if not isinstance(payload, dict):
        raise WebhookPayloadError("El payload JSON debe ser un objeto.")

    return payload


def has_meta_webhook_shape(payload: dict[str, Any]) -> bool:
    """Valida de forma mínima la estructura esperada de Meta."""
    return is_meta_payload(payload)


def process_post_payload(raw_body: bytes) -> dict[str, Any]:
    """Procesa de forma segura un POST recibido en el webhook.

    Fase 2.9:
    - Decodifica payload.
    - Registra errores de payload no procesable.
    - Extrae mensajes entrantes con payload_parser.
    - Valida remitentes desde instruction_service/security_service.
    - Crea WhatsAppInstruccion y WhatsAppBitacora.
    - No ejecuta movimientos operativos del ERP.
    """
    try:
        payload = decode_payload(raw_body)
    except WebhookPayloadError as exc:
        logger.warning("Payload inválido recibido en webhook WhatsApp: %s", exc)
        _registrar_error_seguro_desde_raw(raw_body, str(exc))
        return {
            "status": "ok",
            "received": False,
            "detail": "invalid_payload",
        }

    if not payload:
        logger.info("Webhook WhatsApp recibió POST vacío.")
        return {
            "status": "ok",
            "received": True,
            "detail": "empty_payload",
        }

    if not has_meta_webhook_shape(payload):
        logger.warning("Webhook WhatsApp recibió payload sin estructura esperada de Meta.")
        _registrar_error_seguro(
            payload,
            "El payload no tiene la estructura esperada de Meta WhatsApp.",
        )
        return {
            "status": "ok",
            "received": True,
            "detail": "unexpected_payload_shape",
        }

    try:
        messages = extract_messages(payload)
        statuses = extract_status_updates(payload)
    except Exception as exc:  # pragma: no cover - protección ante cambios de payload Meta
        logger.exception("No fue posible parsear el payload de WhatsApp.")
        _registrar_error_seguro(payload, f"Error al parsear payload: {exc}")
        return {
            "status": "ok",
            "received": True,
            "detail": "payload_parse_error",
        }

    if statuses and not messages:
        logger.info("Webhook WhatsApp recibió status update. statuses=%s", len(statuses))
        return {
            "status": "ok",
            "received": True,
            "detail": "status_update_received",
            "messages": 0,
            "statuses": len(statuses),
        }

    persistence_summary = persist_incoming_messages(payload, messages)

    logger.info(
        "Webhook WhatsApp procesado. messages=%s statuses=%s created=%s duplicates=%s authorized=%s unauthorized=%s inactive=%s errors=%s",
        len(messages),
        len(statuses),
        persistence_summary["created"],
        persistence_summary["duplicates"],
        persistence_summary["authorized"],
        persistence_summary["unauthorized"],
        persistence_summary["inactive"],
        persistence_summary["errors"],
    )

    return {
        "status": "ok",
        "received": True,
        "detail": "payload_received",
        "messages": len(messages),
        "statuses": len(statuses),
        "persistence": persistence_summary,
    }


def persist_incoming_messages(payload: dict[str, Any], messages: list[dict[str, Any]]) -> dict[str, int]:
    """Guarda cada mensaje entrante como WhatsAppInstruccion."""
    summary = {
        "created": 0,
        "duplicates": 0,
        "authorized": 0,
        "unauthorized": 0,
        "inactive": 0,
        "errors": 0,
    }

    for message in messages:
        try:
            result = crear_instruccion_desde_payload(payload, message)
        except DatabaseError:
            logger.exception("Error de base de datos al guardar instrucción WhatsApp.")
            summary["errors"] += 1
            continue
        except Exception:
            logger.exception("Error inesperado al guardar instrucción WhatsApp.")
            summary["errors"] += 1
            continue

        if result.duplicate:
            summary["duplicates"] += 1
            continue

        if result.created:
            summary["created"] += 1

        if result.inactive_sender:
            summary["inactive"] += 1
        elif result.authorized:
            summary["authorized"] += 1
        else:
            summary["unauthorized"] += 1

    return summary


def _registrar_error_seguro(payload: dict[str, Any], error: str) -> None:
    try:
        registrar_error(error=error, payload_original=payload)
    except Exception:
        logger.exception("No fue posible registrar error de payload WhatsApp.")


def _registrar_error_seguro_desde_raw(raw_body: bytes, error: str) -> None:
    try:
        registrar_error_desde_raw_payload(raw_body, error)
    except Exception:
        logger.exception("No fue posible registrar error de payload raw WhatsApp.")
