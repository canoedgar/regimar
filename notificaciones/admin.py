from django.contrib import admin

from .models import NotificacionCorreo, ReporteProgramado


@admin.register(NotificacionCorreo)
class NotificacionCorreoAdmin(admin.ModelAdmin):
    list_display = ("creado_en", "tipo", "asunto", "estado", "enviado_en", "enviado_por")
    list_filter = ("tipo", "estado", "creado_en", "enviado_en")
    search_fields = ("asunto", "destinatarios", "mensaje_error")
    readonly_fields = ("creado_en", "enviado_en", "mensaje_error")


@admin.register(ReporteProgramado)
class ReporteProgramadoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "tipo", "activo", "hora_envio", "dias_a_reportar", "ultimo_envio")
    list_filter = ("activo", "tipo")
    search_fields = ("nombre", "destinatarios")
