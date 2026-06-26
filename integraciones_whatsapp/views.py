from __future__ import annotations

import json
from datetime import datetime, time

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from accounts.decorators import administrador_requerido

from .forms import (
    WhatsAppInstruccionFiltroForm,
    WhatsAppRemitenteAutorizadoForm,
    WhatsAppRemitenteFiltroForm,
)
from .models import WhatsAppInstruccion, WhatsAppRemitenteAutorizado
from .services.security_service import (
    get_request_signature,
    is_webhook_enabled,
    should_validate_signature,
    validate_meta_signature,
    validate_verify_token,
)
from .services.webhook_service import process_post_payload

import logging

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def whatsapp_webhook(request):
    """Endpoint base para Meta WhatsApp Cloud API.

    - GET: valida el hub.challenge enviado por Meta.
    - POST: recibe payloads, valida firma si WHATSAPP_APP_SECRET existe y
      delega el procesamiento al servicio del webhook.
    - No ejecuta movimientos del ERP.
    """
    if not is_webhook_enabled():
        logger.warning("Webhook WhatsApp rechazado porque WHATSAPP_WEBHOOK_ENABLED=False.")
        if request.method == "GET":
            return HttpResponse("Webhook de WhatsApp deshabilitado", status=403)
        return JsonResponse({"status": "disabled"}, status=403)

    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        verify_token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge", "")

        if validate_verify_token(mode, verify_token):
            logger.info("Webhook WhatsApp verificado correctamente por Meta.")
            return HttpResponse(challenge, status=200, content_type="text/plain")

        logger.warning("Webhook WhatsApp rechazó una verificación con token inválido.")
        return HttpResponse("Token de verificación inválido", status=403)

    if should_validate_signature():
        signature = get_request_signature(request.headers)
        if not validate_meta_signature(request.body, signature):
            logger.warning("Webhook WhatsApp rechazó POST por firma inválida.")
            return JsonResponse({"status": "invalid_signature"}, status=403)

    result = process_post_payload(request.body)
    return JsonResponse(result, status=200)


@administrador_requerido
def instrucciones_list(request):
    """Bandeja interna para revisar instrucciones recibidas por WhatsApp."""
    form = WhatsAppInstruccionFiltroForm(request.GET or None)
    instrucciones = WhatsAppInstruccion.objects.all()

    if form.is_valid():
        q = (form.cleaned_data.get("q") or "").strip()
        estado = form.cleaned_data.get("estado")
        telefono = (form.cleaned_data.get("telefono") or "").strip()
        tipo_mensaje = (form.cleaned_data.get("tipo_mensaje") or "").strip()
        fecha_desde = form.cleaned_data.get("fecha_desde")
        fecha_hasta = form.cleaned_data.get("fecha_hasta")
        con_error = form.cleaned_data.get("con_error")

        if q:
            instrucciones = instrucciones.filter(
                Q(telefono_origen__icontains=q)
                | Q(nombre_perfil__icontains=q)
                | Q(mensaje_original__icontains=q)
                | Q(mensaje_id_externo__icontains=q)
                | Q(intencion_detectada__icontains=q)
                | Q(error__icontains=q)
            )
        if estado:
            instrucciones = instrucciones.filter(estado=estado)
        if telefono:
            instrucciones = instrucciones.filter(telefono_origen__icontains=telefono)
        if tipo_mensaje:
            instrucciones = instrucciones.filter(tipo_mensaje__icontains=tipo_mensaje)
        if fecha_desde:
            instrucciones = instrucciones.filter(fecha_recibido__gte=_make_aware_datetime(fecha_desde, time.min))
        if fecha_hasta:
            instrucciones = instrucciones.filter(fecha_recibido__lte=_make_aware_datetime(fecha_hasta, time.max))
        if con_error:
            instrucciones = instrucciones.filter(Q(error__isnull=False) & ~Q(error=""))

    resumen = _get_resumen_instrucciones(instrucciones)
    paginator = Paginator(instrucciones, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    for instruccion in page_obj.object_list:
        instruccion.estado_badge_class = _estado_instruccion_badge_class(instruccion.estado)

    return render(
        request,
        "integraciones_whatsapp/instrucciones_list.html",
        {
            "form": form,
            "page_obj": page_obj,
            "instrucciones": page_obj.object_list,
            "resumen": resumen,
            "querystring_sin_pagina": _querystring_without_page(request),
        },
    )


@administrador_requerido
def instruccion_detail(request, pk):
    """Detalle auditable de una instrucción recibida por WhatsApp."""
    instruccion = get_object_or_404(
        WhatsAppInstruccion.objects.prefetch_related("bitacora", "operaciones"),
        pk=pk,
    )
    instruccion.estado_badge_class = _estado_instruccion_badge_class(instruccion.estado)

    operaciones = instruccion.operaciones.select_related("ejecutado_por").all()
    for operacion in operaciones:
        operacion.estado_badge_class = _estado_operacion_badge_class(operacion.estado)

    return render(
        request,
        "integraciones_whatsapp/instruccion_detail.html",
        {
            "instruccion": instruccion,
            "payload_original_json": _json_pretty(instruccion.payload_original),
            "datos_extraidos_json": _json_pretty(instruccion.datos_extraidos_json),
            "bitacora": instruccion.bitacora.all(),
            "operaciones": operaciones,
        },
    )


@administrador_requerido
def remitentes_list(request):
    """Listado interno de números autorizados para WhatsApp."""
    form = WhatsAppRemitenteFiltroForm(request.GET or None, initial={"estado": "activos"})
    remitentes = WhatsAppRemitenteAutorizado.objects.select_related("usuario_sistema").order_by(
        "nombre", "telefono"
    )

    if form.is_valid():
        q = (form.cleaned_data.get("q") or "").strip()
        estado = form.cleaned_data.get("estado") or "activos"

        if q:
            remitentes = remitentes.filter(
                Q(nombre__icontains=q)
                | Q(telefono__icontains=q)
                | Q(usuario_sistema__username__icontains=q)
                | Q(usuario_sistema__email__icontains=q)
            )
        if estado == "activos":
            remitentes = remitentes.filter(activo=True)
        elif estado == "inactivos":
            remitentes = remitentes.filter(activo=False)

    paginator = Paginator(remitentes, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "integraciones_whatsapp/remitentes_list.html",
        {
            "form": form,
            "page_obj": page_obj,
            "remitentes": page_obj.object_list,
            "querystring_sin_pagina": _querystring_without_page(request),
        },
    )


@administrador_requerido
def remitente_create(request):
    """Alta controlada de un remitente autorizado."""
    if request.method == "POST":
        form = WhatsAppRemitenteAutorizadoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Remitente autorizado creado correctamente.")
            return redirect("integraciones_whatsapp:remitentes_list")
    else:
        form = WhatsAppRemitenteAutorizadoForm(initial={"activo": True, "requiere_confirmacion_siempre": True})

    return render(
        request,
        "integraciones_whatsapp/remitente_form.html",
        {"form": form, "titulo": "Nuevo remitente autorizado"},
    )


@administrador_requerido
def remitente_update(request, pk):
    """Edición controlada de un remitente autorizado."""
    remitente = get_object_or_404(WhatsAppRemitenteAutorizado, pk=pk)

    if request.method == "POST":
        form = WhatsAppRemitenteAutorizadoForm(request.POST, instance=remitente)
        if form.is_valid():
            form.save()
            messages.success(request, "Remitente autorizado actualizado correctamente.")
            return redirect("integraciones_whatsapp:remitentes_list")
    else:
        form = WhatsAppRemitenteAutorizadoForm(instance=remitente)

    return render(
        request,
        "integraciones_whatsapp/remitente_form.html",
        {"form": form, "remitente": remitente, "titulo": "Editar remitente autorizado"},
    )


def _make_aware_datetime(fecha, hora):
    value = datetime.combine(fecha, hora)
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _get_resumen_instrucciones(queryset):
    return {
        "total": queryset.count(),
        "recibidas": queryset.filter(estado=WhatsAppInstruccion.ESTADO_RECIBIDA).count(),
        "no_autorizadas": queryset.filter(estado=WhatsAppInstruccion.ESTADO_NO_AUTORIZADA).count(),
        "errores": queryset.filter(estado=WhatsAppInstruccion.ESTADO_ERROR).count(),
    }


def _querystring_without_page(request):
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()


def _json_pretty(value):
    if not value:
        return "{}"
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _estado_instruccion_badge_class(estado):
    mapping = {
        WhatsAppInstruccion.ESTADO_RECIBIDA: "bg-primary",
        WhatsAppInstruccion.ESTADO_NO_AUTORIZADA: "bg-danger",
        WhatsAppInstruccion.ESTADO_INTERPRETADA: "bg-info text-dark",
        WhatsAppInstruccion.ESTADO_PENDIENTE_DATOS: "bg-warning text-dark",
        WhatsAppInstruccion.ESTADO_PENDIENTE_CONFIRMACION: "bg-warning text-dark",
        WhatsAppInstruccion.ESTADO_CONFIRMADA: "bg-success",
        WhatsAppInstruccion.ESTADO_EJECUTADA: "bg-success",
        WhatsAppInstruccion.ESTADO_RECHAZADA: "bg-secondary",
        WhatsAppInstruccion.ESTADO_ERROR: "bg-danger",
        WhatsAppInstruccion.ESTADO_REQUIERE_REVISION: "bg-dark",
    }
    return mapping.get(estado, "bg-secondary")


def _estado_operacion_badge_class(estado):
    mapping = {
        "PENDIENTE": "bg-primary",
        "PENDIENTE_CONFIRMACION": "bg-warning text-dark",
        "EJECUTADA": "bg-success",
        "RECHAZADA": "bg-secondary",
        "CANCELADA": "bg-secondary",
        "ERROR": "bg-danger",
    }
    return mapping.get(estado, "bg-secondary")
