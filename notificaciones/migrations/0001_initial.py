# Generated manually for the notificaciones app setup.

import datetime

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificacionCorreo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo", models.CharField(choices=[("REPORTE_GENERAL", "Reporte general"), ("PRUEBA", "Correo de prueba"), ("OTRO", "Otro")], db_index=True, default="OTRO", max_length=30)),
                ("asunto", models.CharField(max_length=180)),
                ("destinatarios", models.TextField(help_text="Correos separados por coma, punto y coma o salto de línea.")),
                ("estado", models.CharField(choices=[("PENDIENTE", "Pendiente"), ("ENVIADO", "Enviado"), ("ERROR", "Error")], db_index=True, default="PENDIENTE", max_length=12)),
                ("mensaje_error", models.TextField(blank=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("enviado_en", models.DateTimeField(blank=True, null=True)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("enviado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notificaciones_correo_enviadas", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Notificación por correo",
                "verbose_name_plural": "Notificaciones por correo",
                "ordering": ["-creado_en", "-id"],
                "permissions": [("puede_enviar_reportes", "Puede enviar reportes por correo")],
            },
        ),
        migrations.CreateModel(
            name="ReporteProgramado",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(default="Reporte general diario", max_length=120)),
                ("tipo", models.CharField(choices=[("GENERAL", "Reporte general de operación")], default="GENERAL", max_length=20)),
                ("activo", models.BooleanField(default=True)),
                ("destinatarios", models.TextField(help_text="Correos separados por coma, punto y coma o salto de línea.")),
                ("hora_envio", models.TimeField(default=datetime.time(8, 0))),
                ("dias_a_reportar", models.PositiveSmallIntegerField(default=0, help_text="0 = día actual; 1 = día anterior; 7 = últimos 7 días cerrados.")),
                ("ultimo_envio", models.DateTimeField(blank=True, null=True)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Reporte programado",
                "verbose_name_plural": "Reportes programados",
                "ordering": ["nombre"],
            },
        ),
    ]
