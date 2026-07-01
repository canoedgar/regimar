from django.conf import settings
from django.db import models
from django.utils import timezone

from inventarios.models import SalidaInventario, SalidaInventarioDetalle


class NotaVenta(models.Model):
    """Entidad comercial fisica de una nota de venta.

    `salida` conserva el movimiento fisico de inventario. Esta tabla conserva
    identidad comercial, cliente, pago, estado administrativo e impresion.
    """

    TIPO_VENTA = SalidaInventario.TIPO_VENTA

    FORMA_PAGO_CONTADO = "CONTADO"
    FORMA_PAGO_CREDITO = "CREDITO"
    FORMA_PAGO_TERMINAL = "TERMINAL"
    FORMA_PAGO_CHOICES = [
        (FORMA_PAGO_CONTADO, "Contado"),
        (FORMA_PAGO_CREDITO, "Credito"),
        (FORMA_PAGO_TERMINAL, "Terminal bancaria"),
    ]

    ESTADO_PAGO_PAGADO = "PAG"
    ESTADO_PAGO_PENDIENTE = "PEND"
    ESTADO_PAGO_PARCIAL = "PARC"
    ESTADO_PAGO_CHOICES = [
        (ESTADO_PAGO_PAGADO, "Pagado"),
        (ESTADO_PAGO_PENDIENTE, "Pendiente de pago"),
        (ESTADO_PAGO_PARCIAL, "Pago parcial"),
    ]

    LOGO_REGIMAR = "REGIMAR"
    LOGO_NOTA_CHOICES = [
        (LOGO_REGIMAR, "Regimar"),
    ]

    ESTADO_ACTIVA = "ACT"
    ESTADO_CANCELADA = "CAN"
    ESTADO_CHOICES = [
        (ESTADO_ACTIVA, "Activa"),
        (ESTADO_CANCELADA, "Cancelada"),
    ]

    salida = models.OneToOneField(
        SalidaInventario,
        on_delete=models.PROTECT,
        primary_key=True,
        related_name="nota_venta",
    )
    folio = models.CharField("Folio", max_length=20, unique=True)
    fecha = models.DateField("Fecha", default=timezone.now)
    cliente = models.CharField("Cliente", max_length=200, blank=True)
    cliente_ref = models.ForeignKey(
        "catalogos.Cliente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notas_venta",
        help_text="Cliente del catalogo usado para historial de precios.",
    )
    forma_pago_venta = models.CharField("Forma de pago de venta", max_length=10, choices=FORMA_PAGO_CHOICES, default=FORMA_PAGO_CONTADO)
    estado_pago = models.CharField("Estado de pago", max_length=4, choices=ESTADO_PAGO_CHOICES, default=ESTADO_PAGO_PENDIENTE, db_index=True)
    comision_terminal_porcentaje = models.DecimalField("Comision terminal (%)", max_digits=7, decimal_places=4, default=0)
    comision_terminal_monto = models.DecimalField("Comision terminal", max_digits=14, decimal_places=2, default=0)
    cliente_direccion = models.TextField("Direccion del cliente para esta venta", blank=True)
    cliente_contacto = models.CharField("Contacto del cliente para esta venta", max_length=200, blank=True)
    logo_nota = models.CharField("Logo", max_length=20, choices=LOGO_NOTA_CHOICES, default=LOGO_REGIMAR)
    documento_referencia = models.CharField("Documento referencia", max_length=60, blank=True)
    motivo = models.TextField("Motivo", blank=True)
    observaciones = models.TextField("Observaciones", blank=True)
    estado = models.CharField("Estado", max_length=3, choices=ESTADO_CHOICES, default=ESTADO_ACTIVA, db_index=True)
    cancelada_en = models.DateTimeField("Cancelada en", null=True, blank=True)
    motivo_cancelacion = models.TextField("Motivo de cancelacion", blank=True)
    editada_en = models.DateTimeField("Editada en", null=True, blank=True)
    editada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="notas_venta_comerciales_editadas")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Nota de venta"
        verbose_name_plural = "Notas de venta"
        ordering = ["-fecha", "-folio"]

    @property
    def id(self):
        return self.salida_id

    @property
    def tipo(self):
        return self.TIPO_VENTA

    @tipo.setter
    def tipo(self, value):
        # Compatibilidad con el antiguo proxy: el tipo comercial siempre es venta.
        pass

    @property
    def almacen(self):
        return self.salida.almacen

    @almacen.setter
    def almacen(self, value):
        self.salida.almacen = value

    @property
    def almacen_id(self):
        return self.salida.almacen_id

    @property
    def registrado_por(self):
        return self.salida.registrado_por

    @registrado_por.setter
    def registrado_por(self, value):
        self.salida.registrado_por = value

    @property
    def detalles(self):
        return self.salida.detalles

    @property
    def logo_nota_static_path(self):
        return "resources/regimar.jpg"

    def get_tipo_display(self):
        return "Salida por venta"

    def __str__(self):
        return f"{self.folio} - Nota de venta"

    def save(self, *args, **kwargs):
        if not self.salida_id:
            self.salida = SalidaInventario.objects.create(
                folio=self.folio,
                fecha=self.fecha,
                tipo=SalidaInventario.TIPO_VENTA,
                cliente=self.cliente,
                cliente_ref=self.cliente_ref,
                forma_pago_venta=self.forma_pago_venta,
                estado_pago=self.estado_pago,
                comision_terminal_porcentaje=self.comision_terminal_porcentaje,
                comision_terminal_monto=self.comision_terminal_monto,
                cliente_direccion=self.cliente_direccion,
                cliente_contacto=self.cliente_contacto,
                logo_nota=self.logo_nota,
                documento_referencia=self.documento_referencia,
                motivo=self.motivo,
                observaciones=self.observaciones,
                estado=self.estado,
                cancelada_en=self.cancelada_en,
                motivo_cancelacion=self.motivo_cancelacion,
                editada_en=self.editada_en,
                editada_por=self.editada_por,
            )
        super().save(*args, **kwargs)
        self.sincronizar_salida_legacy()

    def sincronizar_salida_legacy(self):
        salida = self.salida
        salida.folio = self.folio
        salida.fecha = self.fecha
        salida.tipo = SalidaInventario.TIPO_VENTA
        salida.cliente = self.cliente
        salida.cliente_ref = self.cliente_ref
        salida.forma_pago_venta = self.forma_pago_venta
        salida.estado_pago = self.estado_pago
        salida.comision_terminal_porcentaje = self.comision_terminal_porcentaje
        salida.comision_terminal_monto = self.comision_terminal_monto
        salida.cliente_direccion = self.cliente_direccion
        salida.cliente_contacto = self.cliente_contacto
        salida.logo_nota = self.logo_nota
        salida.documento_referencia = self.documento_referencia
        salida.motivo = self.motivo
        salida.observaciones = self.observaciones
        salida.estado = self.estado
        salida.cancelada_en = self.cancelada_en
        salida.motivo_cancelacion = self.motivo_cancelacion
        salida.editada_en = self.editada_en
        salida.editada_por = self.editada_por
        salida.save(update_fields=["folio", "fecha", "tipo", "cliente", "cliente_ref", "forma_pago_venta", "estado_pago", "comision_terminal_porcentaje", "comision_terminal_monto", "cliente_direccion", "cliente_contacto", "logo_nota", "documento_referencia", "motivo", "observaciones", "estado", "cancelada_en", "motivo_cancelacion", "editada_en", "editada_por"])


class NotaVentaDetalleManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(salida__nota_venta__isnull=False)


class NotaVentaDetalle(SalidaInventarioDetalle):
    objects = NotaVentaDetalleManager()

    class Meta:
        proxy = True
        verbose_name = "Detalle de nota de venta"
        verbose_name_plural = "Detalles de notas de venta"

    @property
    def nota_venta(self):
        return self.salida.nota_venta
