# catalogos/models.py
from django.db import models
from django.utils import timezone
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
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stock_minimo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stock_maximo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    imagen = models.ImageField(upload_to="productos", blank=True, null=True)
    imagen_base64 = models.TextField(blank=True, null=True)

    es_equipo = models.BooleanField(
        default=False,
        help_text="Indica si el producto es un equipo con número de serie"
    )

    def save(self, *args, **kwargs):
        self.nombre_normalizado = normalizar_nombre(self.nombre)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre

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
    )

    nombre_fiscal = models.CharField(
        "Nombre / Razón social (SAT)",
        max_length=254,
        help_text="Debe coincidir con el nombre registrado ante el SAT.",
    )
    nombre_fiscal_normalizado = models.CharField(
        max_length=260, editable=False, db_index=True
    )

    regimen_fiscal = models.CharField(
    "Régimen fiscal (SAT)",
    max_length=3,
    choices=REGIMEN_FISCAL_CHOICES,
)

    domicilio_fiscal_cp = models.CharField(
        "Domicilio fiscal - CP (SAT)",
        max_length=5,
        validators=[RegexValidator(CP_REGEX, "El CP debe tener 5 dígitos.")],
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
        ordering = ["nombre_fiscal"]
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
        return f"{self.nombre_fiscal} ({self.rfc})"

# --- Fin Clientes ---

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