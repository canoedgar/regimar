import json

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    WhatsAppBitacora,
    WhatsAppInstruccion,
    WhatsAppOperacion,
    WhatsAppRemitenteAutorizado,
)


class WhatsAppOperacionInline(admin.TabularInline):
    model = WhatsAppOperacion
    extra = 0
    fields = (
        "tipo_operacion",
        "app_destino",
        "modelo_afectado",
        "objeto_id",
        "estado",
        "ejecutado_por",
        "fecha_ejecucion",
    )
    readonly_fields = ("fecha_ejecucion",)
    show_change_link = True


class WhatsAppBitacoraInline(admin.TabularInline):
    model = WhatsAppBitacora
    extra = 0
    fields = ("fecha", "evento", "detalle")
    readonly_fields = ("fecha", "evento", "detalle")
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(WhatsAppRemitenteAutorizado)
class WhatsAppRemitenteAutorizadoAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "telefono",
        "usuario_sistema",
        "activo",
        "puede_consultar_stock",
        "puede_cambiar_precios",
        "puede_crear_clientes",
        "puede_registrar_inventario",
        "requiere_confirmacion_siempre",
    )
    list_filter = (
        "activo",
        "puede_consultar_stock",
        "puede_cambiar_precios",
        "puede_crear_clientes",
        "puede_registrar_inventario",
        "requiere_confirmacion_siempre",
        "fecha_creacion",
    )
    search_fields = ("telefono", "nombre", "usuario_sistema__username", "usuario_sistema__email")
    autocomplete_fields = ("usuario_sistema",)
    readonly_fields = ("fecha_creacion", "fecha_actualizacion")
    fieldsets = (
        ("Datos del remitente", {
            "fields": ("telefono", "nombre", "usuario_sistema", "activo"),
        }),
        ("Permisos operativos", {
            "fields": (
                "puede_consultar_stock",
                "puede_cambiar_precios",
                "puede_crear_clientes",
                "puede_registrar_inventario",
                "requiere_confirmacion_siempre",
            ),
        }),
        ("Auditoría", {
            "fields": ("fecha_creacion", "fecha_actualizacion"),
        }),
    )


@admin.register(WhatsAppInstruccion)
class WhatsAppInstruccionAdmin(admin.ModelAdmin):
    list_display = (
        "fecha_recibido",
        "telefono_origen",
        "nombre_perfil",
        "tipo_mensaje",
        "estado",
        "intencion_detectada",
    )
    list_filter = (
        "estado",
        "tipo_mensaje",
        "proveedor",
        "requiere_confirmacion",
        "fecha_recibido",
    )
    search_fields = (
        "telefono_origen",
        "nombre_perfil",
        "mensaje_original",
        "mensaje_id_externo",
        "intencion_detectada",
    )
    readonly_fields = (
        "payload_original_legible",
        "datos_extraidos_legible",
        "fecha_recibido",
        "fecha_procesado",
        "fecha_confirmacion",
    )
    inlines = (WhatsAppOperacionInline, WhatsAppBitacoraInline)
    fieldsets = (
        ("Origen", {
            "fields": (
                "proveedor",
                "telefono_origen",
                "nombre_perfil",
                "mensaje_id_externo",
                "tipo_mensaje",
                "fecha_recibido",
            ),
        }),
        ("Mensaje", {
            "fields": ("mensaje_original", "payload_original_legible"),
        }),
        ("Estado e interpretación", {
            "fields": (
                "estado",
                "intencion_detectada",
                "datos_extraidos_legible",
                "confianza",
                "requiere_confirmacion",
                "codigo_confirmacion",
                "fecha_confirmacion",
                "fecha_procesado",
            ),
        }),
        ("Respuesta y errores", {
            "fields": ("respuesta_enviada", "error"),
        }),
    )

    def payload_original_legible(self, obj):
        return self._json_pretty(obj.payload_original)

    payload_original_legible.short_description = "Payload original"

    def datos_extraidos_legible(self, obj):
        return self._json_pretty(obj.datos_extraidos_json)

    datos_extraidos_legible.short_description = "Datos extraídos"

    @staticmethod
    def _json_pretty(value):
        if not value:
            return "-"
        pretty = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        return format_html("<pre style='white-space: pre-wrap; max-width: 100%;'>{}</pre>", pretty)


@admin.register(WhatsAppOperacion)
class WhatsAppOperacionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tipo_operacion",
        "app_destino",
        "modelo_afectado",
        "objeto_id",
        "estado",
        "ejecutado_por",
        "fecha_ejecucion",
    )
    list_filter = ("tipo_operacion", "estado", "app_destino", "fecha_ejecucion")
    search_fields = (
        "resumen",
        "app_destino",
        "modelo_afectado",
        "objeto_id",
        "instruccion__telefono_origen",
        "instruccion__mensaje_original",
    )
    autocomplete_fields = ("instruccion", "ejecutado_por")
    readonly_fields = ("fecha_ejecucion",)


@admin.register(WhatsAppBitacora)
class WhatsAppBitacoraAdmin(admin.ModelAdmin):
    list_display = ("fecha", "evento", "telefono_origen", "estado_instruccion")
    list_filter = ("evento", "fecha", "instruccion__estado")
    search_fields = (
        "evento",
        "detalle",
        "instruccion__telefono_origen",
        "instruccion__mensaje_original",
        "instruccion__mensaje_id_externo",
    )
    autocomplete_fields = ("instruccion",)
    readonly_fields = ("fecha",)

    def telefono_origen(self, obj):
        return obj.instruccion.telefono_origen

    telefono_origen.short_description = "Teléfono origen"

    def estado_instruccion(self, obj):
        return obj.instruccion.get_estado_display()

    estado_instruccion.short_description = "Estado instrucción"
