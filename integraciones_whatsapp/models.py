from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class WhatsAppRemitenteAutorizado(models.Model):
    """Número autorizado para enviar instrucciones al ERP por WhatsApp."""

    telefono = models.CharField(
        "Teléfono",
        max_length=20,
        unique=True,
        help_text="Número en formato internacional. Ejemplo: +526441277600.",
    )
    nombre = models.CharField("Nombre", max_length=120)
    usuario_sistema = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="remitentes_whatsapp_autorizados",
        verbose_name="Usuario del sistema",
    )
    activo = models.BooleanField(default=True)
    puede_consultar_stock = models.BooleanField("Puede consultar stock", default=False)
    puede_cambiar_precios = models.BooleanField("Puede cambiar precios", default=False)
    puede_crear_clientes = models.BooleanField("Puede crear clientes", default=False)
    puede_registrar_inventario = models.BooleanField("Puede registrar inventario", default=False)
    requiere_confirmacion_siempre = models.BooleanField(
        "Requiere confirmación siempre",
        default=True,
        help_text="Obliga confirmación adicional aunque el remitente tenga permisos.",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Remitente autorizado de WhatsApp"
        verbose_name_plural = "Remitentes autorizados de WhatsApp"
        ordering = ["nombre", "telefono"]
        indexes = [
            models.Index(fields=["telefono"], name="wa_rem_tel_idx"),
            models.Index(fields=["activo"], name="wa_rem_activo_idx"),
        ]

    def __str__(self):
        return f"{self.nombre} | {self.telefono}"


class WhatsAppInstruccion(models.Model):
    """Mensaje recibido desde WhatsApp y trazado como instrucción potencial."""

    ESTADO_RECIBIDA = "RECIBIDA"
    ESTADO_NO_AUTORIZADA = "NO_AUTORIZADA"
    ESTADO_INTERPRETADA = "INTERPRETADA"
    ESTADO_PENDIENTE_DATOS = "PENDIENTE_DATOS"
    ESTADO_PENDIENTE_CONFIRMACION = "PENDIENTE_CONFIRMACION"
    ESTADO_CONFIRMADA = "CONFIRMADA"
    ESTADO_EJECUTADA = "EJECUTADA"
    ESTADO_RECHAZADA = "RECHAZADA"
    ESTADO_ERROR = "ERROR"
    ESTADO_REQUIERE_REVISION = "REQUIERE_REVISION"

    ESTADO_CHOICES = [
        (ESTADO_RECIBIDA, "Recibida"),
        (ESTADO_NO_AUTORIZADA, "No autorizada"),
        (ESTADO_INTERPRETADA, "Interpretada"),
        (ESTADO_PENDIENTE_DATOS, "Pendiente de datos"),
        (ESTADO_PENDIENTE_CONFIRMACION, "Pendiente de confirmación"),
        (ESTADO_CONFIRMADA, "Confirmada"),
        (ESTADO_EJECUTADA, "Ejecutada"),
        (ESTADO_RECHAZADA, "Rechazada"),
        (ESTADO_ERROR, "Error"),
        (ESTADO_REQUIERE_REVISION, "Requiere revisión"),
    ]

    proveedor = models.CharField("Proveedor", max_length=30, default="meta")
    telefono_origen = models.CharField("Teléfono origen", max_length=20, blank=True)
    nombre_perfil = models.CharField("Nombre de perfil", max_length=120, blank=True)
    mensaje_id_externo = models.CharField(
        "ID externo del mensaje",
        max_length=120,
        unique=True,
        null=True,
        blank=True,
        help_text="Identificador enviado por Meta. Se usa para evitar duplicados.",
    )
    tipo_mensaje = models.CharField("Tipo de mensaje", max_length=30, blank=True)
    mensaje_original = models.TextField("Mensaje original", blank=True)
    payload_original = models.JSONField("Payload original", default=dict, blank=True)
    estado = models.CharField(
        "Estado",
        max_length=30,
        choices=ESTADO_CHOICES,
        default=ESTADO_RECIBIDA,
    )
    intencion_detectada = models.CharField("Intención detectada", max_length=60, blank=True)
    datos_extraidos_json = models.JSONField("Datos extraídos", default=dict, blank=True)
    confianza = models.DecimalField(
        "Confianza",
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
        help_text="Porcentaje de confianza de interpretación. Rango 0 a 100.",
    )
    requiere_confirmacion = models.BooleanField("Requiere confirmación", default=True)
    codigo_confirmacion = models.CharField("Código de confirmación", max_length=20, blank=True)
    fecha_confirmacion = models.DateTimeField("Fecha de confirmación", null=True, blank=True)
    respuesta_enviada = models.TextField("Respuesta enviada", blank=True)
    error = models.TextField("Error", blank=True)
    fecha_recibido = models.DateTimeField("Fecha recibido", auto_now_add=True)
    fecha_procesado = models.DateTimeField("Fecha procesado", null=True, blank=True)

    class Meta:
        verbose_name = "Instrucción de WhatsApp"
        verbose_name_plural = "Instrucciones de WhatsApp"
        ordering = ["-fecha_recibido", "-id"]
        indexes = [
            models.Index(fields=["telefono_origen"], name="wa_inst_tel_idx"),
            models.Index(fields=["mensaje_id_externo"], name="wa_inst_msg_ext_idx"),
            models.Index(fields=["estado"], name="wa_inst_estado_idx"),
            models.Index(fields=["fecha_recibido"], name="wa_inst_frec_idx"),
            models.Index(fields=["estado", "fecha_recibido"], name="wa_inst_estado_frec_idx"),
        ]

    def __str__(self):
        return f"{self.fecha_recibido:%Y-%m-%d %H:%M} | {self.telefono_origen} | {self.get_estado_display()}"


class WhatsAppOperacion(models.Model):
    """Operación derivada de una instrucción de WhatsApp."""

    TIPO_CONSULTA_STOCK = "CONSULTA_STOCK"
    TIPO_CAMBIO_PRECIO_CLIENTE = "CAMBIO_PRECIO_CLIENTE"
    TIPO_ALTA_CLIENTE_BORRADOR = "ALTA_CLIENTE_BORRADOR"
    TIPO_ENTRADA_INVENTARIO = "ENTRADA_INVENTARIO"

    TIPO_OPERACION_CHOICES = [
        (TIPO_CONSULTA_STOCK, "Consulta de stock"),
        (TIPO_CAMBIO_PRECIO_CLIENTE, "Cambio de precio por cliente"),
        (TIPO_ALTA_CLIENTE_BORRADOR, "Alta de cliente como borrador"),
        (TIPO_ENTRADA_INVENTARIO, "Entrada de inventario"),
    ]

    ESTADO_PENDIENTE = "PENDIENTE"
    ESTADO_PENDIENTE_CONFIRMACION = "PENDIENTE_CONFIRMACION"
    ESTADO_EJECUTADA = "EJECUTADA"
    ESTADO_RECHAZADA = "RECHAZADA"
    ESTADO_CANCELADA = "CANCELADA"
    ESTADO_ERROR = "ERROR"

    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, "Pendiente"),
        (ESTADO_PENDIENTE_CONFIRMACION, "Pendiente de confirmación"),
        (ESTADO_EJECUTADA, "Ejecutada"),
        (ESTADO_RECHAZADA, "Rechazada"),
        (ESTADO_CANCELADA, "Cancelada"),
        (ESTADO_ERROR, "Error"),
    ]

    instruccion = models.ForeignKey(
        WhatsAppInstruccion,
        on_delete=models.CASCADE,
        related_name="operaciones",
        verbose_name="Instrucción",
    )
    tipo_operacion = models.CharField(
        "Tipo de operación",
        max_length=40,
        choices=TIPO_OPERACION_CHOICES,
    )
    app_destino = models.CharField("App destino", max_length=60, blank=True)
    modelo_afectado = models.CharField("Modelo afectado", max_length=120, blank=True)
    objeto_id = models.CharField("ID de objeto", max_length=80, blank=True)
    resumen = models.TextField("Resumen", blank=True)
    estado = models.CharField(
        "Estado",
        max_length=30,
        choices=ESTADO_CHOICES,
        default=ESTADO_PENDIENTE,
    )
    ejecutado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operaciones_whatsapp_ejecutadas",
        verbose_name="Ejecutado por",
    )
    fecha_ejecucion = models.DateTimeField("Fecha de ejecución", null=True, blank=True)

    class Meta:
        verbose_name = "Operación de WhatsApp"
        verbose_name_plural = "Operaciones de WhatsApp"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["tipo_operacion"], name="wa_op_tipo_idx"),
            models.Index(fields=["estado"], name="wa_op_estado_idx"),
            models.Index(fields=["app_destino", "modelo_afectado"], name="wa_op_destino_idx"),
        ]

    def __str__(self):
        return f"{self.get_tipo_operacion_display()} | {self.get_estado_display()}"


class WhatsAppBitacora(models.Model):
    """Bitácora auditable de eventos ocurridos sobre una instrucción."""

    instruccion = models.ForeignKey(
        WhatsAppInstruccion,
        on_delete=models.CASCADE,
        related_name="bitacora",
        verbose_name="Instrucción",
    )
    evento = models.CharField("Evento", max_length=120)
    detalle = models.TextField("Detalle", blank=True)
    fecha = models.DateTimeField("Fecha", auto_now_add=True)

    class Meta:
        verbose_name = "Bitácora de WhatsApp"
        verbose_name_plural = "Bitácora de WhatsApp"
        ordering = ["-fecha", "-id"]
        indexes = [
            models.Index(fields=["evento"], name="wa_bit_evento_idx"),
            models.Index(fields=["fecha"], name="wa_bit_fecha_idx"),
        ]

    def __str__(self):
        return f"{self.fecha:%Y-%m-%d %H:%M} | {self.evento}"
