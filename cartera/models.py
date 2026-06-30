from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


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
