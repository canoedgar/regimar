from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class CotizacionPrecio(models.Model):
    ESTATUS_BORRADOR = "BORRADOR"
    ESTATUS_APROBADA = "APROBADA"
    ESTATUS_CANCELADA = "CANCELADA"
    ESTATUS_VENCIDA = "VENCIDA"

    ESTATUS_CHOICES = [
        (ESTATUS_BORRADOR, "Borrador"),
        (ESTATUS_APROBADA, "Aprobada"),
        (ESTATUS_CANCELADA, "Cancelada"),
        (ESTATUS_VENCIDA, "Vencida"),
    ]

    folio = models.CharField(max_length=30, unique=True, db_index=True)
    cliente = models.ForeignKey(
        "catalogos.Cliente",
        on_delete=models.PROTECT,
        related_name="cotizaciones_precio",
        null=True,
        blank=True,
        help_text="Cliente existente del sistema.",
    )

    # Campos heredados de la primera versión. Se conservan para no romper migraciones/BD.
    prospecto_nombre = models.CharField(max_length=180, blank=True)
    prospecto_contacto = models.CharField(max_length=150, blank=True)
    prospecto_telefono = models.CharField(max_length=30, blank=True)
    prospecto_email = models.EmailField(blank=True)
    prospecto_direccion = models.TextField(blank=True)

    fecha = models.DateField(default=timezone.localdate)
    fecha_vigencia = models.DateField()
    estatus = models.CharField(max_length=20, choices=ESTATUS_CHOICES, default=ESTATUS_BORRADOR)
    observaciones = models.TextField(blank=True)
    fecha_autorizacion = models.DateTimeField(null=True, blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cotizaciones_precio_creadas",
    )
    autorizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cotizaciones_precio_autorizadas",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cotización de precios"
        verbose_name_plural = "Cotizaciones de precios"
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return self.folio

    @property
    def nombre_cliente(self):
        if self.cliente_id:
            return self.cliente.nombre_fiscal or str(self.cliente)
        return self.prospecto_nombre or "—"

    @property
    def direccion_cliente(self):
        if self.cliente_id:
            partes = [
                self.cliente.calle,
                self.cliente.num_ext,
                f"Int. {self.cliente.num_int}" if self.cliente.num_int else "",
                self.cliente.colonia,
                self.cliente.localidad,
                self.cliente.municipio,
                self.cliente.estado,
                f"CP {self.cliente.cp}" if self.cliente.cp else "",
            ]
            return ", ".join([p for p in partes if p])
        return self.prospecto_direccion

    @property
    def contacto_cliente(self):
        if self.cliente_id:
            return self.cliente.contacto or self.cliente.telefono or self.cliente.email_cfdi
        return self.prospecto_contacto or self.prospecto_telefono or self.prospecto_email

    @property
    def vencida_por_fecha(self):
        return self.estatus == self.ESTATUS_BORRADOR and self.fecha_vigencia < timezone.localdate()

    @property
    def total_estimado(self):
        return sum((d.importe_estimado or Decimal("0.00") for d in self.detalles.all()), Decimal("0.00"))

    @property
    def utilidad_total_estimada(self):
        return sum((d.utilidad_total_estimada or Decimal("0.00") for d in self.detalles.all()), Decimal("0.00"))

    def marcar_vencida_si_aplica(self, guardar=True):
        if self.vencida_por_fecha:
            self.estatus = self.ESTATUS_VENCIDA
            if guardar:
                self.save(update_fields=["estatus", "updated_at"])
        return self.estatus == self.ESTATUS_VENCIDA


class CotizacionPrecioDetalle(models.Model):
    cotizacion = models.ForeignKey(CotizacionPrecio, on_delete=models.CASCADE, related_name="detalles")
    producto = models.ForeignKey(
        "catalogos.Producto",
        on_delete=models.PROTECT,
        related_name="cotizaciones_precio_detalle",
    )
    cantidad_estimada = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Cantidad estimada en la unidad base del producto. No afecta inventario.",
    )
    cantidad_cajas = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Cantidad informativa de cajas/piezas cuando aplique. No afecta inventario.",
    )
    costo_base = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(Decimal("0.00"))])
    precio_sugerido = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(Decimal("0.00"))])
    precio_minimo = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(Decimal("0.00"))])
    precio_propuesto = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    margen_porcentaje = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    utilidad_unitaria = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    importe_estimado = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    utilidad_total_estimada = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    unidad_precio = models.CharField(max_length=20, default="KG")
    requiere_autorizacion = models.BooleanField(default=False)
    autorizado = models.BooleanField(default=False)
    observaciones = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Detalle de cotización de precios"
        verbose_name_plural = "Detalles de cotización de precios"
        ordering = ["producto__nombre"]
        unique_together = ("cotizacion", "producto")

    def __str__(self):
        return f"{self.cotizacion} | {self.producto}"
