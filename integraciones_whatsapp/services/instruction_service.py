"""Servicio para crear y actualizar instrucciones recibidas por WhatsApp.

Fase 2.9:
    Convierte mensajes parseados desde Meta en registros WhatsAppInstruccion,
    valida remitente autorizado, evita duplicados y registra bitácora.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction

from integraciones_whatsapp.models import WhatsAppInstruccion, WhatsAppRemitenteAutorizado

from .audit_service import registrar_evento
from .security_service import normalize_phone, validate_authorized_sender

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InstructionResult:
    """Resultado controlado de creación de una instrucción."""

    instruccion: WhatsAppInstruccion | None
    created: bool
    duplicate: bool
    status: str
    authorized: bool = False
    inactive_sender: bool = False
    error: str = ""


def crear_instruccion_desde_payload(
    payload_original: dict[str, Any],
    mensaje_parseado: dict[str, Any],
) -> InstructionResult:
    """Crea una instrucción a partir de un mensaje entrante parseado.

    No ejecuta acciones del ERP. Solo persiste el mensaje, valida el remitente
    y registra trazabilidad.
    """
    if not isinstance(mensaje_parseado, dict):
        raise ValueError("mensaje_parseado debe ser un diccionario.")

    mensaje_id_externo = _get_message_external_id(mensaje_parseado)
    instruccion_existente = evitar_duplicados(mensaje_id_externo)
    if instruccion_existente:
        logger.info("Mensaje WhatsApp duplicado ignorado. message_id=%s", mensaje_id_externo)
        return InstructionResult(
            instruccion=instruccion_existente,
            created=False,
            duplicate=True,
            status=instruccion_existente.estado,
            authorized=instruccion_existente.estado != WhatsAppInstruccion.ESTADO_NO_AUTORIZADA,
        )

    telefono_origen = normalize_phone(mensaje_parseado.get("from"))
    remitente_autorizado, remitente = _resolver_remitente(telefono_origen)
    estado = _estado_inicial(remitente_autorizado)
    requiere_confirmacion = _requiere_confirmacion(remitente) if remitente_autorizado else False

    defaults = {
        "proveedor": getattr(settings, "WHATSAPP_PROVIDER", "meta") or "meta",
        "telefono_origen": telefono_origen,
        "nombre_perfil": str(mensaje_parseado.get("profile_name") or "").strip()[:120],
        "mensaje_id_externo": mensaje_id_externo,
        "tipo_mensaje": str(mensaje_parseado.get("message_type") or "unknown").strip()[:30],
        "mensaje_original": str(mensaje_parseado.get("text") or "").strip(),
        "payload_original": payload_original if isinstance(payload_original, dict) else {},
        "estado": estado,
        "datos_extraidos_json": _datos_extraidos_iniciales(mensaje_parseado, remitente),
        "requiere_confirmacion": requiere_confirmacion,
    }

    try:
        with transaction.atomic():
            instruccion = WhatsAppInstruccion.objects.create(**defaults)
            registrar_evento(instruccion, "Mensaje recibido", _detalle_mensaje_recibido(mensaje_parseado))

            if remitente_autorizado:
                registrar_evento(instruccion, "Remitente autorizado", _detalle_remitente(remitente))
            elif remitente:
                marcar_no_autorizada(instruccion, "El remitente existe, pero está inactivo.")
            else:
                marcar_no_autorizada(instruccion, "El número no está registrado como remitente autorizado.")

    except IntegrityError:
        instruccion = evitar_duplicados(mensaje_id_externo)
        if instruccion:
            logger.info("Mensaje WhatsApp duplicado controlado por restricción única. message_id=%s", mensaje_id_externo)
            return InstructionResult(
                instruccion=instruccion,
                created=False,
                duplicate=True,
                status=instruccion.estado,
                authorized=instruccion.estado != WhatsAppInstruccion.ESTADO_NO_AUTORIZADA,
            )
        raise

    return InstructionResult(
        instruccion=instruccion,
        created=True,
        duplicate=False,
        status=instruccion.estado,
        authorized=instruccion.estado == WhatsAppInstruccion.ESTADO_RECIBIDA,
        inactive_sender=bool(remitente and not remitente.activo),
    )


def marcar_no_autorizada(instruccion: WhatsAppInstruccion, detalle: str = "") -> WhatsAppInstruccion:
    """Marca una instrucción como no autorizada y registra bitácora."""
    campos_actualizados = []

    if instruccion.estado != WhatsAppInstruccion.ESTADO_NO_AUTORIZADA:
        instruccion.estado = WhatsAppInstruccion.ESTADO_NO_AUTORIZADA
        campos_actualizados.append("estado")

    if detalle and instruccion.error != detalle:
        instruccion.error = detalle
        campos_actualizados.append("error")

    if campos_actualizados:
        instruccion.save(update_fields=campos_actualizados)

    registrar_evento(
        instruccion,
        "Remitente no autorizado",
        detalle or "El número no tiene permiso para enviar instrucciones al ERP.",
    )
    return instruccion


def marcar_recibida(instruccion: WhatsAppInstruccion, detalle: str = "") -> WhatsAppInstruccion:
    """Marca una instrucción como recibida y registra bitácora."""
    if instruccion.estado != WhatsAppInstruccion.ESTADO_RECIBIDA:
        instruccion.estado = WhatsAppInstruccion.ESTADO_RECIBIDA
        instruccion.save(update_fields=["estado"])

    registrar_evento(instruccion, "Instrucción recibida", detalle)
    return instruccion


def registrar_error(
    error: str,
    payload_original: dict[str, Any] | None = None,
    telefono_origen: str = "",
    mensaje_original: str = "",
    mensaje_id_externo: str | None = None,
) -> InstructionResult:
    """Registra una instrucción en estado ERROR por payload no procesable."""
    mensaje_id_externo = mensaje_id_externo or _build_error_message_id(payload_original, error, mensaje_original)
    existente = evitar_duplicados(mensaje_id_externo)
    if existente:
        return InstructionResult(
            instruccion=existente,
            created=False,
            duplicate=True,
            status=existente.estado,
            error=existente.error,
        )

    with transaction.atomic():
        instruccion = WhatsAppInstruccion.objects.create(
            proveedor=getattr(settings, "WHATSAPP_PROVIDER", "meta") or "meta",
            telefono_origen=normalize_phone(telefono_origen),
            mensaje_id_externo=mensaje_id_externo,
            tipo_mensaje="payload",
            mensaje_original=mensaje_original or "",
            payload_original=payload_original or {},
            estado=WhatsAppInstruccion.ESTADO_ERROR,
            requiere_confirmacion=False,
            error=str(error or "Error no especificado").strip(),
        )
        registrar_evento(instruccion, "Error de validación", instruccion.error)

    return InstructionResult(
        instruccion=instruccion,
        created=True,
        duplicate=False,
        status=instruccion.estado,
        error=instruccion.error,
    )


def registrar_error_desde_raw_payload(raw_body: bytes, error: str) -> InstructionResult:
    """Registra error cuando el body recibido no puede convertirse a JSON."""
    raw_text = _safe_decode(raw_body)
    payload_original = {
        "raw_body_preview": raw_text[:2000],
        "raw_body_sha256": hashlib.sha256(raw_body or b"").hexdigest(),
    }
    return registrar_error(
        error=error,
        payload_original=payload_original,
        mensaje_original=raw_text[:500],
        mensaje_id_externo=f"error-raw-{payload_original['raw_body_sha256']}",
    )


def evitar_duplicados(mensaje_id_externo: str | None) -> WhatsAppInstruccion | None:
    """Devuelve la instrucción existente si el mensaje externo ya fue recibido."""
    if not mensaje_id_externo:
        return None
    return WhatsAppInstruccion.objects.filter(mensaje_id_externo=mensaje_id_externo).first()


def _resolver_remitente(telefono_origen: str) -> tuple[bool, WhatsAppRemitenteAutorizado | None]:
    autorizado, remitente = validate_authorized_sender(telefono_origen)
    return autorizado, remitente


def _estado_inicial(remitente_autorizado: bool) -> str:
    if remitente_autorizado:
        return WhatsAppInstruccion.ESTADO_RECIBIDA
    return WhatsAppInstruccion.ESTADO_NO_AUTORIZADA


def _requiere_confirmacion(remitente: WhatsAppRemitenteAutorizado | None) -> bool:
    if remitente and remitente.requiere_confirmacion_siempre:
        return True
    return bool(getattr(settings, "WHATSAPP_REQUIRE_CONFIRMATION", True))


def _get_message_external_id(mensaje_parseado: dict[str, Any]) -> str:
    message_id = str(mensaje_parseado.get("message_id") or "").strip()
    if message_id:
        return message_id[:120]

    fingerprint = _stable_json_hash(mensaje_parseado)
    return f"sin-id-{fingerprint}"[:120]


def _datos_extraidos_iniciales(
    mensaje_parseado: dict[str, Any],
    remitente: WhatsAppRemitenteAutorizado | None,
) -> dict[str, Any]:
    datos = {
        "timestamp_meta": str(mensaje_parseado.get("timestamp") or ""),
        "telefono_meta": str(mensaje_parseado.get("from") or ""),
    }
    if remitente:
        datos["remitente_autorizado_id"] = remitente.id
        datos["remitente_autorizado_nombre"] = remitente.nombre
    return datos


def _detalle_mensaje_recibido(mensaje_parseado: dict[str, Any]) -> str:
    return (
        f"Tipo={mensaje_parseado.get('message_type') or 'unknown'} | "
        f"Message ID={mensaje_parseado.get('message_id') or 'sin-id'}"
    )


def _detalle_remitente(remitente: WhatsAppRemitenteAutorizado | None) -> str:
    if not remitente:
        return ""
    usuario = getattr(remitente.usuario_sistema, "username", "") if remitente.usuario_sistema_id else ""
    partes = [f"Remitente={remitente.nombre}", f"Teléfono={remitente.telefono}"]
    if usuario:
        partes.append(f"Usuario={usuario}")
    return " | ".join(partes)


def _build_error_message_id(payload_original: dict[str, Any] | None, error: str, mensaje_original: str) -> str:
    base = {
        "payload": payload_original or {},
        "error": str(error or ""),
        "mensaje": str(mensaje_original or ""),
    }
    return f"error-{_stable_json_hash(base)}"[:120]


def _stable_json_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:40]


def _safe_decode(raw_body: bytes) -> str:
    try:
        return (raw_body or b"").decode("utf-8", errors="replace")
    except Exception:  # pragma: no cover - defensa extrema ante entradas inesperadas
        return ""
