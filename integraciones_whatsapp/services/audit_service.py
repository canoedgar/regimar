"""Servicio de auditoría y bitácora para WhatsApp."""

from __future__ import annotations

from typing import Any

from integraciones_whatsapp.models import WhatsAppBitacora, WhatsAppInstruccion


def registrar_evento(
    instruccion: WhatsAppInstruccion,
    evento: str,
    detalle: str = "",
) -> WhatsAppBitacora:
    """Registra un evento auditable para una instrucción.

    La bitácora es intencionalmente simple: cada servicio de aplicación decide
    qué evento registrar y este servicio solo persiste la trazabilidad.
    """
    return WhatsAppBitacora.objects.create(
        instruccion=instruccion,
        evento=str(evento or "Evento").strip()[:120],
        detalle=str(detalle or "").strip(),
    )


def registrar_eventos(
    instruccion: WhatsAppInstruccion,
    eventos: list[dict[str, Any]],
) -> None:
    """Registra varios eventos de bitácora para una instrucción."""
    for evento in eventos:
        if not isinstance(evento, dict):
            continue
        registrar_evento(
            instruccion=instruccion,
            evento=str(evento.get("evento") or "Evento"),
            detalle=str(evento.get("detalle") or ""),
        )
