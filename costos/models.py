import re
import unicodedata
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone


def normalizar_nombre(nombre: str) -> str:
    """
    Normaliza nombres para evitar duplicados visualmente equivalentes.
    Ejemplo: "Flete compra", "FLETE-COMPRA" y "Flete  Compra" se consideran iguales.
    """
    if not nombre:
        return ""
    nfkd = unicodedata.normalize("NFKD", nombre)
    sin_acentos = "".join(c for c in nfkd if not unicodedata.combining(c))
    solo_basico = re.sub(r"[^a-zA-Z0-9\s\-]", "", sin_acentos).upper()
    return re.sub(r"[\s\-]+", " ", solo_basico).strip()


class CategoriaGasto(models.Model):
    TIPO_COMPRA = "COMPRA"
    TIPO_OPERATIVO = "OPERATIVO"
    TIPO_ADMINISTRATIVO = "ADMINISTRATIVO"
    TIPO_LOGISTICO = "LOGISTICO"
    TIPO_ALMACEN = "ALMACEN"
    TIPO_REPARTO = "REPARTO"
    TIPO_FINANCIERO = "FINANCIERO"
    TIPO_OTRO = "OTRO"

    TIPO_CHOICES = [
        (TIPO_COMPRA, "Compra"),
        (TIPO_OPERATIVO, "Operativo"),
        (TIPO_ADMINISTRATIVO, "Administrativo"),
        (TIPO_LOGISTICO, "Logístico"),
        (TIPO_ALMACEN, "Almacén"),
        (TIPO_REPARTO, "Reparto"),
        (TIPO_FINANCIERO, "Financiero"),
        (TIPO_OTRO, "Otro"),
    ]

    DIST_KG_VENDIDO = "KG_VENDIDO"
    DIST_IMPORTE_VENTA = "IMPORTE_VENTA"
    DIST_KG_COMPRADO = "KG_COMPRADO"
    DIST_COSTO_COMPRA = "COSTO_COMPRA"
    DIST_DIRECTO_ENTRADA = "DIRECTO_ENTRADA"
    DIST_MANUAL = "MANUAL"
    DIST_NO_DISTRIBUIR = "NO_DISTRIBUIR"

    METODO_DISTRIBUCION_CHOICES = [
        (DIST_KG_VENDIDO, "Por kg vendido"),
        (DIST_IMPORTE_VENTA, "Por importe vendido"),
        (DIST_KG_COMPRADO, "Por kg comprado"),
        (DIST_COSTO_COMPRA, "Por costo de compra"),
        (DIST_DIRECTO_ENTRADA, "Directo a entrada"),
        (DIST_MANUAL, "Manual por producto"),
        (DIST_NO_DISTRIBUIR, "No distribuir"),
    ]

    nombre = models.CharField(max_length=120)
    nombre_normalizado = models.CharField(max_length=140, editable=False, unique=True)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default=TIPO_OPERATIVO)
    distribuible = models.BooleanField(
        default=True,
        help_text="Indica si los gastos de esta categoría participarán en el costeo real de productos.",
    )
    metodo_default_distribucion = models.CharField(
        "Método default de distribución",
        max_length=25,
        choices=METODO_DISTRIBUCION_CHOICES,
        default=DIST_KG_VENDIDO,
        help_text="Método sugerido al capturar un gasto de esta categoría.",
    )
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Categoría de gasto"
        verbose_name_plural = "Categorías de gastos"
        ordering = ["tipo", "nombre"]
        permissions = [
            ("puede_activar_categoriagasto", "Puede activar o desactivar categorías de gasto"),
        ]

    def save(self, *args, **kwargs):
        self.nombre_normalizado = normalizar_nombre(self.nombre)
        if not self.distribuible:
            self.metodo_default_distribucion = self.DIST_NO_DISTRIBUIR
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre


class GastoDistribucion(models.Model):
    """
    Snapshot de la distribución de un gasto aplicado hacia productos/almacenes.
    No modifica inventario; solo conserva la base y el importe asignado para costeo real.
    """

    gasto = models.ForeignKey(
        "Gasto",
        on_delete=models.CASCADE,
        related_name="distribuciones",
        verbose_name="Gasto",
    )
    producto = models.ForeignKey(
        "catalogos.Producto",
        on_delete=models.PROTECT,
        related_name="gastos_distribuidos",
        verbose_name="Producto",
    )
    almacen = models.ForeignKey(
        "catalogos.Almacen",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gastos_distribuidos",
        verbose_name="Almacén",
    )
    entrada_detalle = models.ForeignKey(
        "inventarios.EntradaInventarioDetalle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gastos_distribuidos",
        verbose_name="Detalle de entrada",
    )
    salida_detalle = models.ForeignKey(
        "ventas.NotaVentaDetalle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gastos_distribuidos",
        verbose_name="Detalle de salida",
    )
    metodo_distribucion = models.CharField(
        "Método de distribución",
        max_length=25,
        choices=CategoriaGasto.METODO_DISTRIBUCION_CHOICES,
    )
    cantidad_base = models.DecimalField(
        "Base de distribución",
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
        help_text="Cantidad, importe o costo usado como base para prorratear el gasto.",
    )
    porcentaje = models.DecimalField(
        "Porcentaje asignado",
        max_digits=9,
        decimal_places=6,
        default=0,
    )
    importe_asignado = models.DecimalField(
        "Importe asignado",
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    costo_unitario_asignado = models.DecimalField(
        "Costo por unidad base",
        max_digits=18,
        decimal_places=6,
        default=0,
        validators=[MinValueValidator(Decimal("0.000000"))],
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Distribución de gasto"
        verbose_name_plural = "Distribuciones de gastos"
        ordering = ["producto__nombre", "almacen__nombre", "id"]
        indexes = [
            models.Index(fields=["gasto", "producto"]),
            models.Index(fields=["producto", "almacen"]),
            models.Index(fields=["metodo_distribucion"]),
        ]

    def __str__(self):
        return f"{self.gasto.folio} | {self.producto} | ${self.importe_asignado}"


class Gasto(models.Model):
    """
    Registro base de gastos operativos, administrativos o directos de compra.
    La distribución a productos se genera al aplicar el gasto para conservar trazabilidad.
    """

    ESTADO_BORRADOR = "BOR"
    ESTADO_APLICADO = "APL"
    ESTADO_CANCELADO = "CAN"
    ESTADO_CHOICES = [
        (ESTADO_BORRADOR, "Borrador"),
        (ESTADO_APLICADO, "Aplicado"),
        (ESTADO_CANCELADO, "Cancelado"),
    ]

    folio = models.CharField("Folio", max_length=30, unique=True, blank=True)
    fecha = models.DateField("Fecha del gasto", default=timezone.now, db_index=True)
    periodo_inicio = models.DateField("Periodo inicio", db_index=True)
    periodo_fin = models.DateField("Periodo fin", db_index=True)
    categoria = models.ForeignKey(
        CategoriaGasto,
        on_delete=models.PROTECT,
        related_name="gastos",
        verbose_name="Categoría",
    )
    metodo_distribucion = models.CharField(
        "Método de distribución",
        max_length=25,
        choices=CategoriaGasto.METODO_DISTRIBUCION_CHOICES,
        default=CategoriaGasto.DIST_KG_VENDIDO,
        help_text="Método que se usará para distribuir automáticamente el gasto al costeo real al aplicarlo.",
    )
    proveedor = models.ForeignKey(
        "catalogos.Proveedor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gastos_costeo",
        verbose_name="Proveedor",
    )
    entrada_inventario = models.ForeignKey(
        "inventarios.EntradaInventario",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gastos_costeo",
        verbose_name="Entrada de inventario relacionada",
        help_text="Úsalo cuando el gasto pertenece directamente a una entrada, por ejemplo un flete de compra.",
    )
    almacen = models.ForeignKey(
        "catalogos.Almacen",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gastos_costeo",
        verbose_name="Almacén",
    )
    importe = models.DecimalField(
        "Importe",
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    referencia = models.CharField(
        "Referencia",
        max_length=120,
        blank=True,
        help_text="Factura, recibo, transferencia, nota o documento soporte.",
    )
    descripcion = models.TextField("Descripción", blank=True)
    observaciones = models.TextField("Observaciones", blank=True)
    estado = models.CharField(
        "Estado",
        max_length=3,
        choices=ESTADO_CHOICES,
        default=ESTADO_BORRADOR,
        db_index=True,
    )
    motivo_cancelacion = models.TextField("Motivo de cancelación", blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gastos_creados",
    )
    aplicado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gastos_aplicados",
    )
    cancelado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gastos_cancelados",
    )
    aplicado_en = models.DateTimeField("Aplicado en", null=True, blank=True)
    cancelado_en = models.DateTimeField("Cancelado en", null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Gasto"
        verbose_name_plural = "Gastos"
        ordering = ["-fecha", "-creado_en"]
        indexes = [
            models.Index(fields=["fecha", "estado"]),
            models.Index(fields=["periodo_inicio", "periodo_fin"]),
            models.Index(fields=["categoria", "estado"]),
        ]
        permissions = [
            ("puede_aplicar_gasto", "Puede aplicar gastos"),
            ("puede_cancelar_gasto", "Puede cancelar gastos"),
        ]

    def __str__(self):
        return f"{self.folio or 'Gasto'} | {self.categoria} | ${self.importe}"

    @property
    def es_borrador(self):
        return self.estado == self.ESTADO_BORRADOR

    @property
    def es_aplicado(self):
        return self.estado == self.ESTADO_APLICADO

    @property
    def es_cancelado(self):
        return self.estado == self.ESTADO_CANCELADO

    @property
    def puede_editarse(self):
        return self.es_borrador

    @property
    def puede_aplicarse(self):
        return self.es_borrador

    @property
    def puede_cancelarse(self):
        return self.estado in {self.ESTADO_BORRADOR, self.ESTADO_APLICADO}

    @property
    def requiere_distribucion(self):
        return self.metodo_distribucion not in {
            CategoriaGasto.DIST_NO_DISTRIBUIR,
            CategoriaGasto.DIST_MANUAL,
        } and bool(getattr(self.categoria, "distribuible", False))

    @property
    def puede_distribuirse(self):
        return self.es_aplicado and self.requiere_distribucion

    @property
    def importe_distribuido(self):
        return self.distribuciones.aggregate(total=models.Sum("importe_asignado"))["total"] or Decimal("0.00")

    @property
    def base_distribuida(self):
        return self.distribuciones.aggregate(total=models.Sum("cantidad_base"))["total"] or Decimal("0.0000")

    def clean(self):
        super().clean()

        if self.periodo_inicio and self.periodo_fin and self.periodo_inicio > self.periodo_fin:
            raise ValidationError({"periodo_fin": "La fecha final del periodo no puede ser menor a la fecha inicial."})

        if self.categoria_id:
            if not self.categoria.distribuible:
                self.metodo_distribucion = CategoriaGasto.DIST_NO_DISTRIBUIR
            elif self.metodo_distribucion == CategoriaGasto.DIST_NO_DISTRIBUIR:
                raise ValidationError({"metodo_distribucion": "Selecciona un método de distribución para una categoría distribuible."})

        if self.metodo_distribucion == CategoriaGasto.DIST_DIRECTO_ENTRADA and not self.entrada_inventario_id:
            raise ValidationError({"entrada_inventario": "Selecciona la entrada de inventario relacionada para gastos directos a entrada."})

        if self.estado == self.ESTADO_CANCELADO and not (self.motivo_cancelacion or "").strip():
            raise ValidationError({"motivo_cancelacion": "Captura el motivo de cancelación."})

    def save(self, *args, **kwargs):
        if self.categoria_id and not self.categoria.distribuible:
            self.metodo_distribucion = CategoriaGasto.DIST_NO_DISTRIBUIR

        if not self.folio:
            self.folio = self._generar_folio()

        super().save(*args, **kwargs)

    def _generar_folio(self):
        fecha_base = self.fecha or timezone.localdate()
        prefijo = f"GAS-{fecha_base:%Y%m}"
        consecutivo = (
            Gasto.objects.filter(folio__startswith=prefijo)
            .exclude(pk=self.pk)
            .count()
            + 1
        )
        folio = f"{prefijo}-{consecutivo:04d}"
        while Gasto.objects.filter(folio=folio).exclude(pk=self.pk).exists():
            consecutivo += 1
            folio = f"{prefijo}-{consecutivo:04d}"
        return folio

    def aplicar(self, usuario=None):
        if not self.puede_aplicarse:
            raise ValidationError("Solo los gastos en borrador pueden aplicarse.")

        from .services.distribucion import distribuir_gasto

        with transaction.atomic():
            self.full_clean()
            self.estado = self.ESTADO_APLICADO
            self.aplicado_por = usuario if getattr(usuario, "is_authenticated", False) else None
            self.aplicado_en = timezone.now()
            self.save(update_fields=["estado", "aplicado_por", "aplicado_en", "actualizado_en", "metodo_distribucion"])
            distribuir_gasto(self)

    def cancelar(self, usuario=None, motivo=""):
        if not self.puede_cancelarse:
            raise ValidationError("Este gasto ya no puede cancelarse.")

        from .services.distribucion import revertir_distribucion_gasto

        motivo = (motivo or "").strip()
        if not motivo:
            raise ValidationError("Captura el motivo de cancelación.")

        with transaction.atomic():
            revertir_distribucion_gasto(self)
            self.estado = self.ESTADO_CANCELADO
            self.motivo_cancelacion = motivo
            self.cancelado_por = usuario if getattr(usuario, "is_authenticated", False) else None
            self.cancelado_en = timezone.now()
            self.save(update_fields=["estado", "motivo_cancelacion", "cancelado_por", "cancelado_en", "actualizado_en", "metodo_distribucion"])



class CierreCosteoPeriodo(models.Model):
    """
    Fotografía congelada del costeo real para un periodo.
    No modifica inventario ni ventas; resume ventas, costo de compra y gastos distribuidos.
    """

    ESTADO_CERRADO = "CER"
    ESTADO_CANCELADO = "CAN"
    ESTADO_CHOICES = [
        (ESTADO_CERRADO, "Cerrado"),
        (ESTADO_CANCELADO, "Cancelado"),
    ]

    folio = models.CharField("Folio", max_length=30, unique=True, blank=True)
    periodo_inicio = models.DateField("Periodo inicio", db_index=True)
    periodo_fin = models.DateField("Periodo fin", db_index=True)
    estado = models.CharField(
        "Estado",
        max_length=3,
        choices=ESTADO_CHOICES,
        default=ESTADO_CERRADO,
        db_index=True,
    )
    total_productos = models.PositiveIntegerField("Productos", default=0)
    total_movimientos_venta = models.PositiveIntegerField("Movimientos de venta", default=0)
    total_ventas = models.DecimalField("Venta total", max_digits=14, decimal_places=2, default=0)
    total_costo_compra = models.DecimalField("Costo compra total", max_digits=14, decimal_places=2, default=0)
    total_gastos_distribuidos = models.DecimalField("Gastos distribuidos", max_digits=14, decimal_places=2, default=0)
    total_costo_real = models.DecimalField("Costo real total", max_digits=14, decimal_places=2, default=0)
    utilidad_bruta = models.DecimalField("Utilidad bruta", max_digits=14, decimal_places=2, default=0)
    utilidad_real = models.DecimalField("Utilidad real", max_digits=14, decimal_places=2, default=0)
    margen_bruto_porcentaje = models.DecimalField("Margen bruto %", max_digits=8, decimal_places=2, default=0)
    margen_real_porcentaje = models.DecimalField("Margen real %", max_digits=8, decimal_places=2, default=0)
    notas = models.TextField("Notas", blank=True)
    motivo_cancelacion = models.TextField("Motivo de cancelación", blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cierres_costeo_creados",
    )
    cancelado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cierres_costeo_cancelados",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    cancelado_en = models.DateTimeField("Cancelado en", null=True, blank=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cierre de costeo"
        verbose_name_plural = "Cierres de costeo"
        ordering = ["-periodo_inicio", "-folio"]
        indexes = [
            models.Index(fields=["periodo_inicio", "periodo_fin"]),
            models.Index(fields=["estado"]),
        ]
        permissions = [
            ("puede_cancelar_cierre_costeo", "Puede cancelar cierres de costeo"),
        ]

    def __str__(self):
        return f"{self.folio or 'Cierre'} | {self.periodo_inicio:%Y-%m-%d} a {self.periodo_fin:%Y-%m-%d}"

    @property
    def es_cerrado(self):
        return self.estado == self.ESTADO_CERRADO

    @property
    def es_cancelado(self):
        return self.estado == self.ESTADO_CANCELADO

    @property
    def puede_cancelarse(self):
        return self.es_cerrado

    def clean(self):
        super().clean()

        if self.periodo_inicio and self.periodo_fin and self.periodo_inicio > self.periodo_fin:
            raise ValidationError({"periodo_fin": "La fecha final del periodo no puede ser menor a la fecha inicial."})

        if self.periodo_inicio and self.periodo_fin and self.estado != self.ESTADO_CANCELADO:
            qs = CierreCosteoPeriodo.objects.filter(
                periodo_inicio=self.periodo_inicio,
                periodo_fin=self.periodo_fin,
            ).exclude(estado=self.ESTADO_CANCELADO)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError("Ya existe un cierre de costeo vigente para el mismo periodo.")

        if self.estado == self.ESTADO_CANCELADO and not (self.motivo_cancelacion or "").strip():
            raise ValidationError({"motivo_cancelacion": "Captura el motivo de cancelación."})

    def save(self, *args, **kwargs):
        if not self.folio:
            self.folio = self._generar_folio()
        super().save(*args, **kwargs)

    def _generar_folio(self):
        fecha_base = self.periodo_inicio or timezone.localdate()
        prefijo = f"COS-{fecha_base:%Y%m}"
        consecutivo = (
            CierreCosteoPeriodo.objects.filter(folio__startswith=prefijo)
            .exclude(pk=self.pk)
            .count()
            + 1
        )
        folio = f"{prefijo}-{consecutivo:04d}"
        while CierreCosteoPeriodo.objects.filter(folio=folio).exclude(pk=self.pk).exists():
            consecutivo += 1
            folio = f"{prefijo}-{consecutivo:04d}"
        return folio

    def cancelar(self, usuario=None, motivo=""):
        if not self.puede_cancelarse:
            raise ValidationError("Solo se pueden cancelar cierres vigentes.")

        motivo = (motivo or "").strip()
        if not motivo:
            raise ValidationError("Captura el motivo de cancelación.")

        self.estado = self.ESTADO_CANCELADO
        self.motivo_cancelacion = motivo
        self.cancelado_por = usuario if getattr(usuario, "is_authenticated", False) else None
        self.cancelado_en = timezone.now()
        self.full_clean()
        self.save(update_fields=["estado", "motivo_cancelacion", "cancelado_por", "cancelado_en", "actualizado_en"])


class CierreCosteoProducto(models.Model):
    """Detalle por producto de un cierre de costeo."""

    cierre = models.ForeignKey(
        CierreCosteoPeriodo,
        on_delete=models.CASCADE,
        related_name="productos",
        verbose_name="Cierre",
    )
    producto = models.ForeignKey(
        "catalogos.Producto",
        on_delete=models.PROTECT,
        related_name="cierres_costeo",
        verbose_name="Producto",
    )
    cantidad_vendida = models.DecimalField("Cantidad vendida", max_digits=18, decimal_places=4, default=0)
    venta_total = models.DecimalField("Venta total", max_digits=14, decimal_places=2, default=0)
    costo_compra_total = models.DecimalField("Costo compra total", max_digits=14, decimal_places=2, default=0)
    gasto_asignado_total = models.DecimalField("Gasto asignado total", max_digits=14, decimal_places=2, default=0)
    costo_real_total = models.DecimalField("Costo real total", max_digits=14, decimal_places=2, default=0)
    utilidad_bruta = models.DecimalField("Utilidad bruta", max_digits=14, decimal_places=2, default=0)
    utilidad_real = models.DecimalField("Utilidad real", max_digits=14, decimal_places=2, default=0)
    precio_promedio = models.DecimalField("Precio promedio", max_digits=18, decimal_places=6, default=0)
    costo_compra_unitario = models.DecimalField("Costo compra unitario", max_digits=18, decimal_places=6, default=0)
    gasto_unitario = models.DecimalField("Gasto unitario", max_digits=18, decimal_places=6, default=0)
    costo_real_unitario = models.DecimalField("Costo real unitario", max_digits=18, decimal_places=6, default=0)
    margen_bruto_porcentaje = models.DecimalField("Margen bruto %", max_digits=8, decimal_places=2, default=0)
    margen_real_porcentaje = models.DecimalField("Margen real %", max_digits=8, decimal_places=2, default=0)
    movimientos_venta = models.PositiveIntegerField("Movimientos de venta", default=0)

    class Meta:
        verbose_name = "Producto en cierre de costeo"
        verbose_name_plural = "Productos en cierres de costeo"
        ordering = ["producto__nombre"]
        unique_together = ("cierre", "producto")
        indexes = [
            models.Index(fields=["cierre", "producto"]),
            models.Index(fields=["producto"]),
        ]

    def __str__(self):
        return f"{self.cierre.folio} | {self.producto}"
