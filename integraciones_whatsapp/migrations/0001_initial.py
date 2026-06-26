# Generated manually for integraciones_whatsapp phase 2.4.

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WhatsAppInstruccion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("proveedor", models.CharField(default="meta", max_length=30, verbose_name="Proveedor")),
                ("telefono_origen", models.CharField(blank=True, max_length=20, verbose_name="Teléfono origen")),
                ("nombre_perfil", models.CharField(blank=True, max_length=120, verbose_name="Nombre de perfil")),
                ("mensaje_id_externo", models.CharField(blank=True, help_text="Identificador enviado por Meta. Se usa para evitar duplicados.", max_length=120, null=True, unique=True, verbose_name="ID externo del mensaje")),
                ("tipo_mensaje", models.CharField(blank=True, max_length=30, verbose_name="Tipo de mensaje")),
                ("mensaje_original", models.TextField(blank=True, verbose_name="Mensaje original")),
                ("payload_original", models.JSONField(blank=True, default=dict, verbose_name="Payload original")),
                ("estado", models.CharField(choices=[("RECIBIDA", "Recibida"), ("NO_AUTORIZADA", "No autorizada"), ("INTERPRETADA", "Interpretada"), ("PENDIENTE_DATOS", "Pendiente de datos"), ("PENDIENTE_CONFIRMACION", "Pendiente de confirmación"), ("CONFIRMADA", "Confirmada"), ("EJECUTADA", "Ejecutada"), ("RECHAZADA", "Rechazada"), ("ERROR", "Error"), ("REQUIERE_REVISION", "Requiere revisión")], default="RECIBIDA", max_length=30, verbose_name="Estado")),
                ("intencion_detectada", models.CharField(blank=True, max_length=60, verbose_name="Intención detectada")),
                ("datos_extraidos_json", models.JSONField(blank=True, default=dict, verbose_name="Datos extraídos")),
                ("confianza", models.DecimalField(decimal_places=2, default=Decimal("0.00"), help_text="Porcentaje de confianza de interpretación. Rango 0 a 100.", max_digits=5, validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))], verbose_name="Confianza")),
                ("requiere_confirmacion", models.BooleanField(default=True, verbose_name="Requiere confirmación")),
                ("codigo_confirmacion", models.CharField(blank=True, max_length=20, verbose_name="Código de confirmación")),
                ("fecha_confirmacion", models.DateTimeField(blank=True, null=True, verbose_name="Fecha de confirmación")),
                ("respuesta_enviada", models.TextField(blank=True, verbose_name="Respuesta enviada")),
                ("error", models.TextField(blank=True, verbose_name="Error")),
                ("fecha_recibido", models.DateTimeField(auto_now_add=True, verbose_name="Fecha recibido")),
                ("fecha_procesado", models.DateTimeField(blank=True, null=True, verbose_name="Fecha procesado")),
            ],
            options={
                "verbose_name": "Instrucción de WhatsApp",
                "verbose_name_plural": "Instrucciones de WhatsApp",
                "ordering": ["-fecha_recibido", "-id"],
            },
        ),
        migrations.CreateModel(
            name="WhatsAppRemitenteAutorizado",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("telefono", models.CharField(help_text="Número en formato internacional. Ejemplo: +526441277600.", max_length=20, unique=True, verbose_name="Teléfono")),
                ("nombre", models.CharField(max_length=120, verbose_name="Nombre")),
                ("activo", models.BooleanField(default=True)),
                ("puede_consultar_stock", models.BooleanField(default=False, verbose_name="Puede consultar stock")),
                ("puede_cambiar_precios", models.BooleanField(default=False, verbose_name="Puede cambiar precios")),
                ("puede_crear_clientes", models.BooleanField(default=False, verbose_name="Puede crear clientes")),
                ("puede_registrar_inventario", models.BooleanField(default=False, verbose_name="Puede registrar inventario")),
                ("requiere_confirmacion_siempre", models.BooleanField(default=True, help_text="Obliga confirmación adicional aunque el remitente tenga permisos.", verbose_name="Requiere confirmación siempre")),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
                ("usuario_sistema", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="remitentes_whatsapp_autorizados", to=settings.AUTH_USER_MODEL, verbose_name="Usuario del sistema")),
            ],
            options={
                "verbose_name": "Remitente autorizado de WhatsApp",
                "verbose_name_plural": "Remitentes autorizados de WhatsApp",
                "ordering": ["nombre", "telefono"],
            },
        ),
        migrations.CreateModel(
            name="WhatsAppOperacion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo_operacion", models.CharField(choices=[("CONSULTA_STOCK", "Consulta de stock"), ("CAMBIO_PRECIO_CLIENTE", "Cambio de precio por cliente"), ("ALTA_CLIENTE_BORRADOR", "Alta de cliente como borrador"), ("ENTRADA_INVENTARIO", "Entrada de inventario")], max_length=40, verbose_name="Tipo de operación")),
                ("app_destino", models.CharField(blank=True, max_length=60, verbose_name="App destino")),
                ("modelo_afectado", models.CharField(blank=True, max_length=120, verbose_name="Modelo afectado")),
                ("objeto_id", models.CharField(blank=True, max_length=80, verbose_name="ID de objeto")),
                ("resumen", models.TextField(blank=True, verbose_name="Resumen")),
                ("estado", models.CharField(choices=[("PENDIENTE", "Pendiente"), ("PENDIENTE_CONFIRMACION", "Pendiente de confirmación"), ("EJECUTADA", "Ejecutada"), ("RECHAZADA", "Rechazada"), ("CANCELADA", "Cancelada"), ("ERROR", "Error")], default="PENDIENTE", max_length=30, verbose_name="Estado")),
                ("fecha_ejecucion", models.DateTimeField(blank=True, null=True, verbose_name="Fecha de ejecución")),
                ("ejecutado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="operaciones_whatsapp_ejecutadas", to=settings.AUTH_USER_MODEL, verbose_name="Ejecutado por")),
                ("instruccion", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="operaciones", to="integraciones_whatsapp.whatsappinstruccion", verbose_name="Instrucción")),
            ],
            options={
                "verbose_name": "Operación de WhatsApp",
                "verbose_name_plural": "Operaciones de WhatsApp",
                "ordering": ["-id"],
            },
        ),
        migrations.CreateModel(
            name="WhatsAppBitacora",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("evento", models.CharField(max_length=120, verbose_name="Evento")),
                ("detalle", models.TextField(blank=True, verbose_name="Detalle")),
                ("fecha", models.DateTimeField(auto_now_add=True, verbose_name="Fecha")),
                ("instruccion", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bitacora", to="integraciones_whatsapp.whatsappinstruccion", verbose_name="Instrucción")),
            ],
            options={
                "verbose_name": "Bitácora de WhatsApp",
                "verbose_name_plural": "Bitácora de WhatsApp",
                "ordering": ["-fecha", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="whatsappinstruccion",
            index=models.Index(fields=["telefono_origen"], name="wa_inst_tel_idx"),
        ),
        migrations.AddIndex(
            model_name="whatsappinstruccion",
            index=models.Index(fields=["mensaje_id_externo"], name="wa_inst_msg_ext_idx"),
        ),
        migrations.AddIndex(
            model_name="whatsappinstruccion",
            index=models.Index(fields=["estado"], name="wa_inst_estado_idx"),
        ),
        migrations.AddIndex(
            model_name="whatsappinstruccion",
            index=models.Index(fields=["fecha_recibido"], name="wa_inst_frec_idx"),
        ),
        migrations.AddIndex(
            model_name="whatsappinstruccion",
            index=models.Index(fields=["estado", "fecha_recibido"], name="wa_inst_estado_frec_idx"),
        ),
        migrations.AddIndex(
            model_name="whatsappremitenteautorizado",
            index=models.Index(fields=["telefono"], name="wa_rem_tel_idx"),
        ),
        migrations.AddIndex(
            model_name="whatsappremitenteautorizado",
            index=models.Index(fields=["activo"], name="wa_rem_activo_idx"),
        ),
        migrations.AddIndex(
            model_name="whatsappoperacion",
            index=models.Index(fields=["tipo_operacion"], name="wa_op_tipo_idx"),
        ),
        migrations.AddIndex(
            model_name="whatsappoperacion",
            index=models.Index(fields=["estado"], name="wa_op_estado_idx"),
        ),
        migrations.AddIndex(
            model_name="whatsappoperacion",
            index=models.Index(fields=["app_destino", "modelo_afectado"], name="wa_op_destino_idx"),
        ),
        migrations.AddIndex(
            model_name="whatsappbitacora",
            index=models.Index(fields=["evento"], name="wa_bit_evento_idx"),
        ),
        migrations.AddIndex(
            model_name="whatsappbitacora",
            index=models.Index(fields=["fecha"], name="wa_bit_fecha_idx"),
        ),
    ]
