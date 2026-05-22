# catalogos/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import uuid
import re
import unicodedata
from django.core.validators import RegexValidator, MinLengthValidator, MaxLengthValidator, MinValueValidator
from decimal import Decimal

#Funciones de catálogos

def normalizar_nombre(nombre: str) -> str:
    """
    Quita acentos, pasa a mayúsculas y elimina espacios/guiones repetidos.
    Sirve para comparar nombres similares.
    """
    if not nombre:
        return ""
    # Quitar acentos
    nfkd = unicodedata.normalize("NFKD", nombre)
    sin_acentos = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Quitar caracteres raros y pasar a mayúsculas
    solo_basico = re.sub(r"[^a-zA-Z0-9\s\-]", "", sin_acentos).upper()
    # Normalizar espacios/guiones
    compactado = re.sub(r"[\s\-]+", " ", solo_basico).strip()
    return compactado

#Fin funciones de catálogos

#Inicio de categrías para productos

class Categoria(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    nombre_normalizado = models.CharField(
        max_length=120,
        editable=False,
        unique=True,
    )

    def save(self, *args, **kwargs):
        self.nombre_normalizado = normalizar_nombre(self.nombre)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre

#Fin de categorías para productos

class Producto(models.Model):
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="productos",
    )
    nombre = models.CharField(max_length=150)
    nombre_normalizado = models.CharField(
        max_length=160,
        editable=False,
        unique=True,  # clave para evitar duplicados “similares”
    )
    clave_sat = models.CharField(max_length=8, blank=True, null=True)
    metrica = models.CharField(max_length=30)
    # Precio de venta actual. Se mantiene manual e independiente del costo de compra.
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    precio_minimo = models.DecimalField(
        "Precio mínimo autorizado",
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Límite mínimo de venta para proteger margen.",
    )
    ultimo_costo_compra = models.DecimalField(
        "Último costo de compra",
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Último costo registrado en una entrada de inventario.",
    )
    costo_promedio = models.DecimalField(
        "Costo promedio actual",
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Costo promedio ponderado del inventario disponible.",
    )
    fecha_ultima_compra = models.DateField(
        "Fecha última compra",
        null=True,
        blank=True,
    )
    fecha_ultima_actualizacion_precio = models.DateTimeField(
        "Fecha última actualización precio venta",
        null=True,
        blank=True,
    )
    stock = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    stock_minimo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    stock_maximo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    imagen = models.ImageField(upload_to="productos", blank=True, null=True)
    imagen_base64 = models.TextField(blank=True, null=True)

    es_equipo = models.BooleanField(
        default=False,
        help_text="Indica si el producto es un equipo con número de serie"
    )
    maneja_peso_variable = models.BooleanField(
        "Maneja peso variable por caja",
        default=False,
        help_text=(
            "Actívalo cuando el producto entra por cajas con peso real variable. "
            "En entrada manual se capturarán cajas y kilos reales."
        ),
    )

    def save(self, *args, **kwargs):
        self.nombre_normalizado = normalizar_nombre(self.nombre)
        super().save(*args, **kwargs)

    @property
    def margen_estimado(self):
        return (self.precio or Decimal("0")) - (self.costo_promedio or Decimal("0"))

    @property
    def margen_porcentaje(self):
        precio = self.precio or Decimal("0")
        if precio <= 0:
            return Decimal("0")
        return (self.margen_estimado / precio) * Decimal("100")

    def __str__(self):
        return self.nombre


class ProductoPrecioBitacora(models.Model):
    """
    Fotografía diaria del panorama de precios/costos de un producto.
    Se actualiza cuando existe un cambio relevante: entrada, costo promedio,
    cambio de precio de venta o cambio de precio mínimo.
    """
    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name="bitacora_precios",
    )
    fecha = models.DateField(db_index=True)
    precio_venta = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    precio_minimo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ultimo_costo_compra = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    costo_promedio = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stock_actual = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    margen_estimado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    margen_porcentaje = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    motivo = models.CharField(max_length=255, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("producto", "fecha")
        verbose_name = "Bitácora diaria de precio"
        verbose_name_plural = "Bitácora diaria de precios"
        ordering = ["-fecha", "producto__nombre"]

    def __str__(self):
        return f"{self.fecha} | {self.producto} | ${self.precio_venta}"


class ProductoPrecioHistorial(models.Model):
    """Auditoría de cambios manuales de precio de venta/precio mínimo."""
    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name="historial_precios",
    )
    precio_anterior = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    precio_nuevo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    precio_minimo_anterior = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    precio_minimo_nuevo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    motivo = models.CharField(max_length=255, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Historial de cambio de precio"
        verbose_name_plural = "Historial de cambios de precio"
        ordering = ["-creado_en", "producto__nombre"]

    def __str__(self):
        return f"{self.producto} | {self.precio_anterior} -> {self.precio_nuevo}"


class ProductoMetricaConversion(models.Model):
    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name="conversiones_metricas",
    )
    nombre = models.CharField(
        max_length=100,
        help_text="Nombre visible de la presentación. Ejemplo: Caja 10 kgs.",
    )
    nombre_normalizado = models.CharField(max_length=120, editable=False)
    unidad_origen = models.CharField(
        max_length=30,
        help_text="Unidad o presentación que venderá el usuario. Ejemplo: Caja.",
    )
    cantidad_origen = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Cantidad base de la unidad origen. Normalmente 1.",
    )
    factor_conversion = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Cuánto equivale la cantidad origen en la métrica default del producto.",
    )
    activo = models.BooleanField(default=True)
    fecha_alta = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Conversión de métrica"
        verbose_name_plural = "Conversiones de métricas"
        ordering = ["producto__nombre", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["producto", "nombre_normalizado"],
                name="uq_producto_conversion_nombre_normalizado",
            )
        ]

    def save(self, *args, **kwargs):
        self.nombre_normalizado = normalizar_nombre(self.nombre)
        super().save(*args, **kwargs)

    @property
    def metrica_default(self):
        return self.producto.metrica

    @property
    def equivalencia_texto(self):
        def decimal_legible(valor):
            if valor is None:
                return "0"
            texto = format(valor, "f")
            if "." in texto:
                texto = texto.rstrip("0").rstrip(".")
            return texto or "0"

        cantidad_origen = decimal_legible(self.cantidad_origen)
        factor = decimal_legible(self.factor_conversion)

        return f"{cantidad_origen} {self.unidad_origen} = {factor} {self.metrica_default}"

    def convertir_a_default(self, cantidad):
        cantidad = Decimal(cantidad or 0)
        return (cantidad / self.cantidad_origen) * self.factor_conversion

    def __str__(self):
        return f"{self.producto.nombre} - {self.nombre}"

#Inicio proveedores        

class Proveedor(models.Model):
    nombre = models.CharField(max_length=150)
    nombre_normalizado = models.CharField(
        max_length=160,
        editable=False,
        unique=True,
    )
    rfc = models.CharField(max_length=13, blank=True, null=True)
    contacto = models.CharField(max_length=150, blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    direccion = models.TextField(blank=True, null=True)
    activo = models.BooleanField(default=True)
    fecha_alta = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.nombre_normalizado = normalizar_nombre(self.nombre)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre

#Fin proveedores

# --- Proyectos ---

class Proyecto(models.Model):
    class Estado(models.TextChoices):
        PLANEADO = "PLANEADO", "Planeado"
        EN_PROCESO = "EN_PROCESO", "En proceso"
        TERMINADO = "TERMINADO", "Terminado"
        CANCELADO = "CANCELADO", "Cancelado"

    nombre = models.CharField(max_length=50)
    apodo = models.CharField(max_length=50, null=True)
    direccion = models.CharField(max_length=150, null=True)
    descripcion = models.TextField(blank=True, null=True)

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PLANEADO,
    )

    fecha_inicio = models.DateField(default=timezone.now)
    fecha_fin = models.DateField(blank=True, null=True)  # solo cuando se termina

    fecha_alta = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Si no está terminado, no debe tener fecha_fin
        if self.estado != self.Estado.TERMINADO:
            self.fecha_fin = None
        else:
            # Si está terminado y no trae fecha_fin, se asigna hoy
            if not self.fecha_fin:
                self.fecha_fin = timezone.now().date()

        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre

# --- Fin Proyectos ---

# --- Inicio Clientes ---

def normalizar(texto: str) -> str:
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


RFC_REGEX = r"^[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}$"  # Persona moral 12 / física 13
CP_REGEX = r"^\d{5}$"


class Cliente(models.Model):

    from catalogos.sat_catalogos import (
    REGIMEN_FISCAL_CHOICES,
    USO_CFDI_CHOICES,
    FORMA_PAGO_CHOICES,
    METODO_PAGO_CHOICES,
    )

    class TipoPersona(models.TextChoices):
        FISICA = "FISICA", "Física"
        MORAL = "MORAL", "Moral"

    # =========================
    # Datos CFDI (Receptor) - CFDI 4.0
    # =========================
    tipo_persona = models.CharField(
        max_length=10, choices=TipoPersona.choices, default=TipoPersona.MORAL
    )

    rfc = models.CharField(
        "RFC",
        max_length=13,
        validators=[
            RegexValidator(RFC_REGEX, "RFC inválido (formato SAT)."),
            MinLengthValidator(12),
            MaxLengthValidator(13),
        ],
        unique=True,
        db_index=True,
        blank=True,
        null=True,
    )

    nombre_fiscal = models.CharField(
        "Nombre / Razón social (SAT)",
        max_length=254,
        blank=True,
        help_text="Debe coincidir con el nombre registrado ante el SAT.",
    )
    nombre_fiscal_normalizado = models.CharField(
        max_length=260, editable=False, db_index=True
    )

    regimen_fiscal = models.CharField(
    "Régimen fiscal (SAT)",
    max_length=3,
    choices=REGIMEN_FISCAL_CHOICES,
    blank=True,
)

    domicilio_fiscal_cp = models.CharField(
        "Domicilio fiscal - CP (SAT)",
        max_length=5,
        validators=[RegexValidator(CP_REGEX, "El CP debe tener 5 dígitos.")],
        blank=True,
        help_text="CFDI 4.0 requiere el CP del domicilio fiscal del receptor.",
    )

    uso_cfdi_default = models.CharField(
    "Uso CFDI por defecto (SAT)",
    max_length=4,
    choices=USO_CFDI_CHOICES,
    blank=True,
    )

    email_cfdi = models.EmailField(
        "Email para envío CFDI",
        blank=True,
        help_text="Correo donde se enviará XML/PDF (no obligatorio para timbrar).",
    )

    # =========================
    # Datos comerciales / contacto
    # =========================
    nombre_comercial = models.CharField("Nombre comercial", max_length=150, blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    contacto = models.CharField("Nombre de contacto", max_length=150, blank=True)

    # Dirección “operativa” (para expediente / envío / PDF)
    calle = models.CharField(max_length=120, blank=True)
    num_ext = models.CharField("No. ext.", max_length=20, blank=True)
    num_int = models.CharField("No. int.", max_length=20, blank=True)
    colonia = models.CharField(max_length=120, blank=True)
    localidad = models.CharField(max_length=120, blank=True)
    municipio = models.CharField(max_length=120, blank=True)
    estado = models.CharField(max_length=120, blank=True)
    pais = models.CharField(max_length=60, blank=True, default="México")
    cp = models.CharField("CP (operativo)", max_length=5, blank=True)
    referencias = models.CharField(max_length=200, blank=True)

    # =========================
    # Defaults para facturación (opcional, útil)
    # =========================
    forma_pago_default = models.CharField(
    "Forma de pago default (SAT)",
    max_length=2,
    choices=FORMA_PAGO_CHOICES,
    blank=True,
    )

    metodo_pago_default = models.CharField(
        "Método de pago default (SAT)",
        max_length=3,
        choices=METODO_PAGO_CHOICES,
        blank=True,
    )

    # =========================
    # Control
    # =========================
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre_fiscal", "nombre_comercial"]
        indexes = [
            models.Index(fields=["rfc"]),
            models.Index(fields=["nombre_fiscal_normalizado"]),
        ]

    def save(self, *args, **kwargs):
        # RFC siempre en mayúsculas
        if self.rfc:
            self.rfc = self.rfc.strip().upper()

        self.nombre_fiscal_normalizado = normalizar(self.nombre_fiscal)

        # Si no capturan CP operativo, podemos copiar el fiscal como ayuda
        if not self.cp and self.domicilio_fiscal_cp:
            self.cp = self.domicilio_fiscal_cp

        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre_fiscal or self.nombre_comercial or self.rfc or f"Cliente {self.pk}"

# --- Fin Clientes ---


class ParametroSistema(models.Model):
    """Configuraciones generales extensibles del sistema."""
    clave = models.CharField(max_length=80, unique=True, db_index=True)
    nombre = models.CharField(max_length=120)
    valor = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Parámetro de sistema"
        verbose_name_plural = "Parámetros de sistema"
        ordering = ["clave"]

    def __str__(self):
        return f"{self.clave}: {self.valor}"

    @classmethod
    def get_int(cls, clave, default=0):
        obj = cls.objects.filter(clave=clave, activo=True).first()
        if not obj:
            return default
        try:
            return int(obj.valor)
        except (TypeError, ValueError):
            return default


class ClienteProductoPrecio(models.Model):
    """Último precio otorgado a un cliente por producto."""
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="precios_producto")
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name="precios_cliente")
    ultimo_precio = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    precio_anterior = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    fecha_ultimo_precio = models.DateTimeField(default=timezone.now)
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    observaciones = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ("cliente", "producto")
        verbose_name = "Precio por cliente"
        verbose_name_plural = "Precios por cliente"
        ordering = ["cliente__nombre_fiscal", "producto__nombre"]

    def __str__(self):
        return f"{self.cliente} | {self.producto} | {self.ultimo_precio}"

    @property
    def dias_sin_compra(self):
        if not self.fecha_ultimo_precio:
            return None
        return (timezone.now().date() - self.fecha_ultimo_precio.date()).days

    @property
    def vigente(self):
        dias = ParametroSistema.get_int("PRECIO_VIGENCIA_DIAS", 0)
        if dias <= 0 or not self.fecha_ultimo_precio:
            return True
        return self.fecha_ultimo_precio >= timezone.now() - timedelta(days=dias)


class PrecioMenorMinimoAutorizacion(models.Model):
    """Token para autorizar un precio menor al mínimo permitido."""
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="autorizaciones_precio")
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name="autorizaciones_precio")
    usuario_solicita = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="solicitudes_precio_minimo")
    precio_actual = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    precio_minimo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    precio_solicitado = models.DecimalField(max_digits=12, decimal_places=2)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    expira_en = models.DateTimeField()
    usado_en = models.DateTimeField(null=True, blank=True)
    autorizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="autorizaciones_precio_minimo")

    class Meta:
        verbose_name = "Autorización de precio menor al mínimo"
        verbose_name_plural = "Autorizaciones de precio menor al mínimo"
        ordering = ["-creado_en"]

    @property
    def usado(self):
        return self.usado_en is not None

    @property
    def expirado(self):
        return timezone.now() > self.expira_en

    def puede_usarse(self):
        return not self.usado and not self.expirado


# --- Inicio Almacenes ---

class Almacen(models.Model):
    TIPO_CHOICES = (
        ("FISICO", "Físico"),
        ("VIRTUAL", "Virtual"),
    )

    codigo = models.CharField(
        max_length=20,
        unique=True,
        help_text="Identificador corto del almacén (ej. MATRIZ, VIRT-PROY).",
    )
    nombre = models.CharField(max_length=100)

    tipo = models.CharField(
        max_length=10,
        choices=TIPO_CHOICES,
        default="FISICO",
    )

    ubicacion = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        help_text="Dirección o referencia (solo almacenes físicos).",
    )

    es_activo = models.BooleanField(default=True)

    # Flags para futuro (sin lógica aún)
    permite_ventas = models.BooleanField(default=True)
    permite_transferencias = models.BooleanField(default=True)
    es_virtual_sistema = models.BooleanField(
        default=False,
        help_text="Almacén virtual controlado por el sistema.",
    )

    fecha_alta = models.DateTimeField(auto_now_add=True)

    es_arrendado = models.BooleanField(default=False)

    class TipoCosto(models.TextChoices):
        POR_KILO = "POR KILO", "Por kilo"
        POR_TARIMA = "POR TARIMA", "Por tarima"

    tipo_costo = models.CharField(
        max_length=20,
        choices=TipoCosto.choices,
        null=True,
        blank=True,
        help_text="Aplica solo si el almacén es arrendado."
    )

    costo_almacen = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Aplica solo si el almacén es arrendado."
    )

    vencimiento_dias = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Cada cuántos días vence el pago (solo arrendado)."
    )

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "Almacén"
        verbose_name_plural = "Almacenes"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


# --- Fin Almacenes ---