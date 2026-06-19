from datetime import time

from django.conf import settings
from django.db import models
from django.utils import timezone


class NotificacionCorreo(models.Model):
    """Bitácora de correos emitidos desde el motor de notificaciones."""

    TIPO_REPORTE_GENERAL = "REPORTE_GENERAL"
    TIPO_PRUEBA = "PRUEBA"
    TIPO_OTRO = "OTRO"
    TIPO_CHOICES = [
        (TIPO_REPORTE_GENERAL, "Reporte general"),
        (TIPO_PRUEBA, "Correo de prueba"),
        (TIPO_OTRO, "Otro"),
    ]

    ESTADO_PENDIENTE = "PENDIENTE"
    ESTADO_ENVIADO = "ENVIADO"
    ESTADO_ERROR = "ERROR"
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, "Pendiente"),
        (ESTADO_ENVIADO, "Enviado"),
        (ESTADO_ERROR, "Error"),
    ]

    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES, default=TIPO_OTRO, db_index=True)
    asunto = models.CharField(max_length=180)
    destinatarios = models.TextField(help_text="Correos separados por coma, punto y coma o salto de línea.")
    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE, db_index=True)
    mensaje_error = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notificaciones_correo_enviadas",
    )
    enviado_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Notificación por correo"
        verbose_name_plural = "Notificaciones por correo"
        ordering = ["-creado_en", "-id"]
        permissions = [
            ("puede_enviar_reportes", "Puede enviar reportes por correo"),
        ]

    def marcar_enviado(self):
        self.estado = self.ESTADO_ENVIADO
        self.enviado_en = timezone.now()
        self.mensaje_error = ""
        self.save(update_fields=["estado", "enviado_en", "mensaje_error"])

    def marcar_error(self, error):
        self.estado = self.ESTADO_ERROR
        self.mensaje_error = str(error)
        self.save(update_fields=["estado", "mensaje_error"])

    def __str__(self):
        return f"{self.get_tipo_display()} | {self.asunto} | {self.get_estado_display()}"


class ReporteProgramado(models.Model):
    """Configuración base para automatizar reportes desde cron/Celery en el futuro."""

    TIPO_GENERAL = "GENERAL"
    TIPO_CHOICES = [
        (TIPO_GENERAL, "Reporte general de operación"),
    ]

    nombre = models.CharField(max_length=120, default="Reporte general diario")
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default=TIPO_GENERAL)
    activo = models.BooleanField(default=True)
    destinatarios = models.TextField(help_text="Correos separados por coma, punto y coma o salto de línea.")
    hora_envio = models.TimeField(default=time(8, 0))
    dias_a_reportar = models.PositiveSmallIntegerField(
        default=0,
        help_text="0 = día actual; 1 = día anterior; 7 = últimos 7 días cerrados.",
    )
    ultimo_envio = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Reporte programado"
        verbose_name_plural = "Reportes programados"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre
