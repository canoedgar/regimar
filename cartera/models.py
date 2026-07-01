from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def factura_xml_upload_to(instance, filename):
    suffix = Path(filename or "cfdi.xml").suffix or ".xml"
    uuid = instance.uuid or f"factura-{timezone.now():%Y%m%d%H%M%S}"
    return f"cartera/facturas/{uuid}{suffix.lower()}"


class PagoCliente(models.Model):
    """Entrada de dinero recibida de un cliente.

    El pago puede aplicarse a una o varias notas de venta, aplicarse por FIFO
    o generar saldo a favor cuando excede el saldo pendiente del cliente.
    """

    ORIGEN_MANUAL = "MANUAL"
    ORIGEN_AUTO_NOTA = "AUTO_NOTA"
    ORIGEN_CHOICES = [
        (ORIGEN_MANUAL, "Manual"),
        (ORIGEN_AUTO_NOTA, "Automático por nota pagada"),
    ]

    TIPO_DIRECTO = "DIRECTO"
    TIPO_FIFO = "FIFO"
    TIPO_ANTICIPO = "ANTICIPO"
    TIPO_AUTO = "AUTO"
    TIPO_CHOICES = [
        (TIPO_DIRECTO, "Aplicado a notas específicas"),
        (TIPO_FIFO, "Pago global a notas pendientes"),
        (TIPO_ANTICIPO, "Anticipo / saldo a favor"),
        (TIPO_AUTO, "Pago automático por nota pagada"),
    ]

    ESTADO_ACTIVO = "ACT"
    ESTADO_CANCELADO = "CAN"
    ESTADO_CHOICES = [
        (ESTADO_ACTIVO, "Activo"),
        (ESTADO_CANCELADO, "Cancelado"),
    ]

    cliente = models.ForeignKey(
        "catalogos.Cliente",
        on_delete=models.PROTECT,
        related_name="pagos_cartera",
    )
    fecha = models.DateTimeField(default=timezone.now, db_index=True)
    origen = models.CharField(max_length=10, choices=ORIGEN_CHOICES, default=ORIGEN_MANUAL)
    tipo_aplicacion = models.CharField(max_length=10, choices=TIPO_CHOICES, default=TIPO_DIRECTO)
    monto_recibido = models.DecimalField(max_digits=14, decimal_places=2)
    referencia = models.CharField(max_length=120, blank=True)
    observaciones = models.TextField(blank=True)
    estado = models.CharField(max_length=3, choices=ESTADO_CHOICES, default=ESTADO_ACTIVO, db_index=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pagos_cartera_creados",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    cancelado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pagos_cartera_cancelados",
    )
    cancelado_en = models.DateTimeField(null=True, blank=True)
    motivo_cancelacion = models.TextField(blank=True)

    class Meta:
        verbose_name = "Pago de cliente"
        verbose_name_plural = "Pagos de clientes"
        ordering = ["-fecha", "-id"]
        permissions = [
            ("puede_registrar_pagos", "Puede registrar pagos"),
            ("puede_cancelar_pagos", "Puede cancelar pagos"),
            ("puede_devolver_saldo_favor", "Puede devolver saldo a favor"),
            ("puede_ver_estado_cuenta", "Puede ver estado de cuenta de clientes"),
        ]
        indexes = [
            models.Index(fields=["cliente", "fecha"]),
            models.Index(fields=["estado"]),
            models.Index(fields=["tipo_aplicacion"]),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(monto_recibido__gt=0), name="pago_cliente_monto_recibido_gt_0"),
        ]

    def __str__(self):
        return f"Pago {self.id} - {self.cliente} - ${self.monto_recibido}"

    @property
    def total_aplicado(self):
        return self.aplicaciones.aggregate(total=models.Sum("monto_aplicado"))["total"] or Decimal("0.00")

    @property
    def saldo_no_aplicado(self):
        return self.monto_recibido - self.total_aplicado

    def clean(self):
        if self.monto_recibido is not None and self.monto_recibido <= 0:
            raise ValidationError({"monto_recibido": "El monto recibido debe ser mayor a cero."})


class PagoMetodoDetalle(models.Model):
    METODO_EFECTIVO = "EFECTIVO"
    METODO_TRANSFERENCIA = "TRANSFERENCIA"
    METODO_TARJETA = "TARJETA"
    METODO_CHEQUE = "CHEQUE"
    METODO_OTRO = "OTRO"
    METODO_CHOICES = [
        (METODO_EFECTIVO, "Efectivo"),
        (METODO_TRANSFERENCIA, "Transferencia"),
        (METODO_TARJETA, "Tarjeta"),
        (METODO_CHEQUE, "Cheque"),
        (METODO_OTRO, "Otro"),
    ]

    pago = models.ForeignKey(PagoCliente, on_delete=models.CASCADE, related_name="metodos")
    metodo = models.CharField(max_length=20, choices=METODO_CHOICES)
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    referencia = models.CharField(max_length=120, blank=True)

    class Meta:
        verbose_name = "Método de pago"
        verbose_name_plural = "Métodos de pago"
        constraints = [
            models.CheckConstraint(condition=models.Q(monto__gt=0), name="pago_metodo_monto_gt_0"),
        ]

    def __str__(self):
        return f"{self.get_metodo_display()} - ${self.monto}"


class PagoAplicacionNota(models.Model):
    """Conciliación entre una entrada de pago y una nota de venta."""

    pago = models.ForeignKey(PagoCliente, on_delete=models.PROTECT, related_name="aplicaciones")
    nota_venta = models.ForeignKey(
        "ventas.NotaVenta",
        on_delete=models.PROTECT,
        related_name="aplicaciones_cartera",
    )
    monto_aplicado = models.DecimalField(max_digits=14, decimal_places=2)
    saldo_antes = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    saldo_despues = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    aplicado_en = models.DateTimeField(auto_now_add=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="aplicaciones_cartera_creadas",
    )
    observaciones = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Aplicación de pago a nota"
        verbose_name_plural = "Aplicaciones de pagos a notas"
        ordering = ["nota_venta__fecha", "nota_venta__folio", "id"]
        indexes = [
            models.Index(fields=["nota_venta"]),
            models.Index(fields=["pago"]),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(monto_aplicado__gt=0), name="aplicacion_nota_monto_gt_0"),
        ]

    def __str__(self):
        return f"{self.pago_id} -> {self.nota_venta} (${self.monto_aplicado})"

    def clean(self):
        if self.pago_id and self.nota_venta_id and self.pago.cliente_id != self.nota_venta.cliente_ref_id:
            raise ValidationError("El pago y la nota de venta deben pertenecer al mismo cliente.")
        if self.monto_aplicado is not None and self.monto_aplicado <= 0:
            raise ValidationError({"monto_aplicado": "El monto aplicado debe ser mayor a cero."})


class ClienteSaldoFavorMovimiento(models.Model):
    """Libro mayor de saldo a favor del cliente.

    Los montos siempre se guardan positivos; el tipo define si suma o resta al
    saldo disponible del cliente.
    """

    TIPO_GENERACION = "GEN"
    TIPO_APLICACION = "APL"
    TIPO_DEVOLUCION = "DEV"
    TIPO_CANCELACION = "CAN"
    TIPO_CHOICES = [
        (TIPO_GENERACION, "Generación de saldo a favor"),
        (TIPO_APLICACION, "Aplicación de saldo a favor"),
        (TIPO_DEVOLUCION, "Devolución de saldo a favor"),
        (TIPO_CANCELACION, "Cancelación / reversa"),
    ]

    cliente = models.ForeignKey(
        "catalogos.Cliente",
        on_delete=models.PROTECT,
        related_name="movimientos_saldo_favor_cartera",
    )
    tipo = models.CharField(max_length=3, choices=TIPO_CHOICES)
    fecha = models.DateTimeField(default=timezone.now, db_index=True)
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    pago_origen = models.ForeignKey(
        PagoCliente,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movimientos_saldo_favor",
    )
    nota_aplicada = models.ForeignKey(
        "ventas.NotaVenta",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movimientos_saldo_favor_cartera",
    )
    metodo_devolucion = models.CharField(max_length=20, blank=True)
    referencia = models.CharField(max_length=120, blank=True)
    observaciones = models.TextField(blank=True)
    autorizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="saldos_favor_cartera_autorizados",
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="saldos_favor_cartera_creados",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Movimiento de saldo a favor"
        verbose_name_plural = "Movimientos de saldo a favor"
        ordering = ["-fecha", "-id"]
        indexes = [
            models.Index(fields=["cliente", "fecha"]),
            models.Index(fields=["tipo"]),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(monto__gt=0), name="saldo_favor_movimiento_monto_gt_0"),
        ]

    def __str__(self):
        return f"{self.cliente} - {self.get_tipo_display()} - ${self.monto}"

    def clean(self):
        if self.monto is not None and self.monto <= 0:
            raise ValidationError({"monto": "El monto debe ser mayor a cero."})
        if self.tipo == self.TIPO_DEVOLUCION and not self.autorizado_por_id:
            raise ValidationError({"autorizado_por": "La devolución debe registrar el usuario que autoriza."})

class FacturaCliente(models.Model):
    """CFDI cargado manualmente para control interno de facturación."""

    TIPO_GLOBAL = "GLOBAL"
    TIPO_NOTAS = "NOTAS"
    TIPO_APLICACION_CHOICES = [
        (TIPO_GLOBAL, "Global al cliente"),
        (TIPO_NOTAS, "Aplicada a notas"),
    ]

    ESTADO_ACTIVA = "ACT"
    ESTADO_CANCELADA = "CAN"
    ESTADO_CHOICES = [
        (ESTADO_ACTIVA, "Activa"),
        (ESTADO_CANCELADA, "Cancelada"),
    ]

    cliente = models.ForeignKey(
        "catalogos.Cliente",
        on_delete=models.PROTECT,
        related_name="facturas_cartera",
    )
    fecha = models.DateTimeField(db_index=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    uuid = models.CharField("UUID fiscal", max_length=36, db_index=True)
    serie = models.CharField(max_length=40, blank=True)
    folio = models.CharField(max_length=40, blank=True)
    tipo_comprobante = models.CharField(max_length=5, blank=True)
    tipo_aplicacion = models.CharField(
        max_length=10,
        choices=TIPO_APLICACION_CHOICES,
        default=TIPO_GLOBAL,
        db_index=True,
        help_text="Define si la factura queda global al cliente o relacionada a notas específicas.",
    )
    moneda = models.CharField(max_length=8, blank=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    descuento = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    impuestos_trasladados = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    impuestos_retenidos = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=14, decimal_places=2)
    total_xml = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Total leído del XML. El total operativo puede capturarse manualmente sin alterar el archivo.",
    )
    rfc_emisor = models.CharField(max_length=13, blank=True)
    nombre_emisor = models.CharField(max_length=254, blank=True)
    rfc_receptor = models.CharField(max_length=13, blank=True)
    nombre_receptor = models.CharField(max_length=254, blank=True)
    uso_cfdi = models.CharField(max_length=4, blank=True)
    forma_pago = models.CharField(max_length=2, blank=True)
    metodo_pago = models.CharField(max_length=3, blank=True)
    xml = models.FileField(upload_to=factura_xml_upload_to)
    xml_hash = models.CharField(max_length=64, db_index=True)
    estado = models.CharField(max_length=3, choices=ESTADO_CHOICES, default=ESTADO_ACTIVA, db_index=True)
    referencia = models.CharField(max_length=120, blank=True)
    observaciones = models.TextField(blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="facturas_cartera_creadas",
    )
    cancelado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="facturas_cartera_canceladas",
    )
    cancelado_en = models.DateTimeField(null=True, blank=True)
    motivo_cancelacion = models.TextField(blank=True)

    class Meta:
        verbose_name = "Factura de cliente"
        verbose_name_plural = "Facturas de clientes"
        ordering = ["-fecha", "-id"]
        permissions = [
            ("puede_registrar_facturas", "Puede registrar facturas"),
            ("puede_cancelar_facturas", "Puede cancelar facturas"),
            ("puede_ver_facturacion", "Puede ver facturación"),
        ]
        indexes = [
            models.Index(fields=["cliente", "fecha"]),
            models.Index(fields=["estado"]),
            models.Index(fields=["tipo_aplicacion"]),
            models.Index(fields=["uuid"]),
            models.Index(fields=["xml_hash"]),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(total__gt=0), name="factura_cliente_total_gt_0"),
        ]

    def __str__(self):
        folio = "-".join(part for part in [self.serie, self.folio] if part) or self.uuid
        return f"{folio} - {self.cliente}"

    @property
    def folio_display(self):
        return "-".join(part for part in [self.serie, self.folio] if part) or self.uuid

    @property
    def total_aplicado_notas(self):
        return self.aplicaciones.aggregate(total=models.Sum("monto_facturado"))["total"] or Decimal("0.00")

    @property
    def total_xml_display(self):
        return self.total_xml or Decimal("0.00")

    @property
    def monto_sin_aplicar_notas(self):
        if self.tipo_aplicacion != self.TIPO_NOTAS:
            return self.total
        return max(self.total - self.total_aplicado_notas, Decimal("0.00"))

    def clean(self):
        if self.total is not None and self.total <= 0:
            raise ValidationError({"total": "El total de la factura debe ser mayor a cero."})
        if self.tipo_aplicacion not in {self.TIPO_GLOBAL, self.TIPO_NOTAS}:
            raise ValidationError({"tipo_aplicacion": "Selecciona el tipo de aplicación de la factura."})
        if not self.uuid:
            raise ValidationError({"uuid": "El XML debe contener UUID fiscal."})
        if self.cliente_id and self.rfc_receptor and self.cliente.rfc:
            if self.rfc_receptor.upper() != self.cliente.rfc.upper():
                raise ValidationError({"rfc_receptor": "El RFC receptor del XML no coincide con el cliente."})


class FacturaAplicacionNota(models.Model):
    """Relación informativa entre una factura y notas de venta."""

    factura = models.ForeignKey(FacturaCliente, on_delete=models.PROTECT, related_name="aplicaciones")
    nota_venta = models.ForeignKey(
        "ventas.NotaVenta",
        on_delete=models.PROTECT,
        related_name="facturas_cartera_aplicadas",
    )
    monto_facturado = models.DecimalField(max_digits=14, decimal_places=2)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="aplicaciones_facturas_cartera_creadas",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    observaciones = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Aplicación de factura a nota"
        verbose_name_plural = "Aplicaciones de facturas a notas"
        ordering = ["nota_venta__fecha", "nota_venta__folio", "id"]
        indexes = [
            models.Index(fields=["factura"]),
            models.Index(fields=["nota_venta"]),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(monto_facturado__gt=0), name="factura_aplicacion_monto_gt_0"),
            models.UniqueConstraint(fields=["factura", "nota_venta"], name="factura_aplicacion_nota_unica"),
        ]

    def __str__(self):
        return f"{self.factura_id} -> {self.nota_venta} (${self.monto_facturado})"

    def clean(self):
        if self.factura_id and self.nota_venta_id and self.factura.cliente_id != self.nota_venta.cliente_ref_id:
            raise ValidationError("La factura y la nota de venta deben pertenecer al mismo cliente.")
        if self.monto_facturado is not None and self.monto_facturado <= 0:
            raise ValidationError({"monto_facturado": "El monto facturado debe ser mayor a cero."})

