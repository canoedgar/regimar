# catalogos/forms.py

#Productos
from django import forms

from accounts.widgets import UniversalDateInput, UNIVERSAL_DATE_INPUT_FORMATS
from django.forms import inlineformset_factory
from .models import Producto, Categoria, Proveedor, Proyecto, Cliente, Almacen, ProductoMetricaConversion, ParametroSistema, ClienteProductoPrecio
from .sat_catalogos import REGIMEN_FISCAL_CHOICES
from .services.regimenes_fiscales import codigos_regimenes_fiscales, regimen_fiscal_a_json

from django.core.exceptions import ValidationError


from PIL import Image
import base64
import io

def imagen_a_base64_comprimida(
    uploaded_file,
    max_size=(256, 256),
    max_bytes=80 * 1024,  # ~80 KB aprox
):
    """
    - Redimensiona la imagen manteniendo proporción, máx 256x256
    - Convierte a JPEG
    - Baja calidad hasta que el tamaño sea <= max_bytes (o calidad mínima 40)
    - Devuelve la cadena Base64 (str)
    """
    if not uploaded_file:
        return None

    # Abrimos la imagen desde el archivo subido
    img = Image.open(uploaded_file)

    # Convertimos a RGB por si viene en RGBA/P u otro modo
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # Redimensionar manteniendo proporción sin exceder max_size
    img.thumbnail(max_size, Image.LANCZOS)

    buffer = io.BytesIO()
    calidad = 85  # punto de inicio

    while calidad >= 40:
        buffer.seek(0)
        buffer.truncate(0)

        img.save(buffer, format="JPEG", optimize=True, quality=calidad)
        size = buffer.tell()

        if size <= max_bytes:
            break

        calidad -= 5  # reducimos la calidad y volvemos a probar

    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")

#Inicio de categorías

class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nombre"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control"})
        }

#Fin de categorías


#Inicio de productos

class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = [
            "categoria",
            "nombre",
            "metrica",
            "precio",
            "precio_minimo",
            "ultimo_costo_compra",
            "costo_promedio",
            "stock",
            "stock_minimo",
            "stock_maximo",
            "maneja_peso_variable",
        ]
        widgets = {
            "categoria": forms.Select(attrs={"class": "form-select"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "metrica": forms.TextInput(attrs={"class": "form-control", "readonly": "readonly"}),
            "precio": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "precio_minimo": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "ultimo_costo_compra": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "costo_promedio": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "stock": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "stock_minimo": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "stock_maximo": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "maneja_peso_variable": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk and not self.initial.get("metrica"):
            self.initial["metrica"] = "KG"
        self.fields["metrica"].disabled = True
        self.fields["metrica"].initial = self.initial.get("metrica") or getattr(self.instance, "metrica", None) or "KG"
        for field_name in ["stock", "ultimo_costo_compra", "costo_promedio"]:
            self.fields[field_name].disabled = True
            self.fields[field_name].widget.attrs["readonly"] = True

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.metrica = "KG"
        instance.es_equipo = False
        if commit:
            instance.save()
        return instance


class ProductoMetricaConversionForm(forms.ModelForm):
    class Meta:
        model = ProductoMetricaConversion
        fields = [
            "nombre",
            "unidad_origen",
            "cantidad_origen",
            "factor_conversion",
            "activo",
        ]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Caja 10 kgs"}),
            "unidad_origen": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Caja"}),
            "cantidad_origen": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
            "factor_conversion": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        self.producto = kwargs.pop("producto", None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        if self.cleaned_data.get("DELETE"):
            return cleaned

        nombre = cleaned.get("nombre")
        unidad_origen = cleaned.get("unidad_origen")
        cantidad_origen = cleaned.get("cantidad_origen")
        factor_conversion = cleaned.get("factor_conversion")

        if any([nombre, unidad_origen, cantidad_origen, factor_conversion]) and not all([
            nombre,
            unidad_origen,
            cantidad_origen,
            factor_conversion,
        ]):
            raise ValidationError("Completa todos los campos de la conversión o elimina la fila vacía.")

        if cantidad_origen and factor_conversion and factor_conversion <= 0:
            self.add_error("factor_conversion", "El factor de conversión debe ser mayor a 0.")

        if cantidad_origen and cantidad_origen <= 0:
            self.add_error("cantidad_origen", "La cantidad origen debe ser mayor a 0.")

        return cleaned


ProductoMetricaConversionFormSet = inlineformset_factory(
    Producto,
    ProductoMetricaConversion,
    form=ProductoMetricaConversionForm,
    extra=0,
    can_delete=True,
)

#Fin Productos

#Inicio proveedores

class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = [
            "nombre",
            "rfc",
            "contacto",
            "telefono",
            "email",
            "direccion",
            "activo",
        ]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "rfc": forms.TextInput(attrs={"class": "form-control"}),
            "contacto": forms.TextInput(attrs={"class": "form-control"}),
            "telefono": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "direccion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


#Fin Proveedores

# --- Inicio Proyectos ---

class ProyectoForm(forms.ModelForm):
    class Meta:
        model = Proyecto
        fields = [
            "nombre", 
            "apodo",
            "direccion",
            "descripcion", 
            "estado", 
            "fecha_inicio", 
            "fecha_fin"
        ]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "apodo": forms.TextInput(attrs={"class": "form-control"}),
            "direccion": forms.TextInput(attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "estado": forms.Select(attrs={"class": "form-select"}),
            "fecha_inicio": UniversalDateInput(),
            "fecha_fin": UniversalDateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fecha_inicio"].input_formats = UNIVERSAL_DATE_INPUT_FORMATS
        self.fields["fecha_fin"].input_formats = UNIVERSAL_DATE_INPUT_FORMATS

    def clean(self):
        cleaned = super().clean()
        estado = cleaned.get("estado")
        fecha_fin = cleaned.get("fecha_fin")

        # Si termina, fecha_fin puede venir vacía (se setea en save), pero si viene, ok
        if estado != Proyecto.Estado.TERMINADO:
            cleaned["fecha_fin"] = None

        return cleaned

# --- Fin Proyectos ---

# --- Inicio Clientes ---

class ParametroSistemaForm(forms.ModelForm):
    class Meta:
        model = ParametroSistema
        fields = ["clave", "nombre", "valor", "descripcion", "activo"]
        widgets = {
            "clave": forms.TextInput(attrs={"class": "form-control", "style": "text-transform: uppercase;"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "valor": forms.TextInput(attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_clave(self):
        return (self.cleaned_data.get("clave") or "").strip().upper()


class ClienteProductoPrecioForm(forms.ModelForm):
    class Meta:
        model = ClienteProductoPrecio
        fields = ["ultimo_precio", "observaciones"]
        widgets = {
            "ultimo_precio": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "observaciones": forms.TextInput(attrs={"class": "form-control"}),
        }


class ClienteForm(forms.ModelForm):
    constancia_situacion_fiscal_pdf = forms.FileField(
        label="Constancia de situación fiscal (PDF)",
        required=False,
        help_text="Carga el PDF emitido por el SAT para llenar automáticamente los datos fiscales y de domicilio.",
        widget=forms.ClearableFileInput(attrs={
            "class": "form-control",
            "accept": "application/pdf,.pdf",
        }),
    )
    regimen_fiscal = forms.MultipleChoiceField(
        label="Regímenes fiscales (SAT)",
        choices=REGIMEN_FISCAL_CHOICES,
        required=False,
        help_text="Selecciona uno o más regímenes fiscales del cliente.",
        widget=forms.SelectMultiple(attrs={
            "class": "form-select",
            "size": "6",
        }),
    )

    class Meta:
        model = Cliente
        fields = [
            # CFDI
            "tipo_persona",
            "rfc",
            "nombre_fiscal",
            "regimen_fiscal",
            "domicilio_fiscal_cp",
            "uso_cfdi_default",
            "email_cfdi",

            # Comerciales
            "nombre_comercial",
            "telefono",
            "contacto",
            "logo",
            "limite_credito",
            "dias_credito",

            # Dirección operativa
            "calle",
            "num_ext",
            "num_int",
            "colonia",
            "localidad",
            "municipio",
            "estado",
            "pais",
            "cp",
            "referencias",

            # Defaults factura
            "forma_pago_default",
            "metodo_pago_default",

            # Control
            "activo",
        ]

        widgets = {
            "tipo_persona": forms.Select(attrs={"class": "form-select"}),

            "rfc": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: XAXX010101000",
                "style": "text-transform: uppercase;",
                "autocomplete": "off",
            }),
            "nombre_fiscal": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Nombre/Razón social como en el SAT",
            }),
            "domicilio_fiscal_cp": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: 83290",
                "autocomplete": "off",
            }),
            "uso_cfdi_default": forms.Select(attrs={"class": "form-select"}),
            "email_cfdi": forms.EmailInput(attrs={
                "class": "form-control",
                "placeholder": "correo@cliente.com",
            }),

            "nombre_comercial": forms.TextInput(attrs={"class": "form-control"}),
            "telefono": forms.TextInput(attrs={"class": "form-control"}),
            "contacto": forms.TextInput(attrs={"class": "form-control", "placeholder": "Nombre de la persona de contacto"}),
            "logo": forms.Select(attrs={"class": "form-select"}),
            "limite_credito": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "0.01"}),
            "dias_credito": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "1"}),

            "calle": forms.TextInput(attrs={"class": "form-control"}),
            "num_ext": forms.TextInput(attrs={"class": "form-control"}),
            "num_int": forms.TextInput(attrs={"class": "form-control"}),
            "colonia": forms.TextInput(attrs={"class": "form-control"}),
            "localidad": forms.TextInput(attrs={"class": "form-control"}),
            "municipio": forms.TextInput(attrs={"class": "form-control"}),
            "estado": forms.TextInput(attrs={"class": "form-control"}),
            "pais": forms.TextInput(attrs={"class": "form-control"}),
            "cp": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: 83290"}),
            "referencias": forms.TextInput(attrs={"class": "form-control"}),

            "forma_pago_default": forms.Select(attrs={"class": "form-select"}),
            "metodo_pago_default": forms.Select(attrs={"class": "form-select"}),

            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        self.puede_editar_parametros_cartera = kwargs.pop("puede_editar_parametros_cartera", True)
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk and not self.is_bound:
            self.fields["regimen_fiscal"].initial = codigos_regimenes_fiscales(self.instance.regimen_fiscal)

        if not self.puede_editar_parametros_cartera:
            self.fields.pop("limite_credito", None)
            self.fields.pop("dias_credito", None)

        if not self.instance.pk:
            self.fields["municipio"].initial = "MEXICALI"
            self.fields["estado"].initial = "B.C."
            self.fields["pais"].initial = "MÉXICO"
            if "limite_credito" in self.fields:
                self.fields["limite_credito"].initial = "3000.00"
            if "dias_credito" in self.fields:
                self.fields["dias_credito"].initial = 1

    def clean_rfc(self):
        rfc = (self.cleaned_data.get("rfc") or "").strip().upper()
        return rfc or None

    def clean_regimen_fiscal(self):
        return regimen_fiscal_a_json(self.cleaned_data.get("regimen_fiscal") or [])

    def clean_constancia_situacion_fiscal_pdf(self):
        archivo = self.cleaned_data.get("constancia_situacion_fiscal_pdf")
        if not archivo:
            return archivo

        nombre = (getattr(archivo, "name", "") or "").lower()
        if not nombre.endswith(".pdf"):
            raise ValidationError("La constancia debe ser un archivo PDF.")

        if getattr(archivo, "size", 0) > 5 * 1024 * 1024:
            raise ValidationError("El PDF no debe exceder 5 MB.")

        return archivo

    def clean(self):
        cleaned = super().clean()
        mp = (cleaned.get("metodo_pago_default") or "").strip().upper()
        if mp and mp not in ("PUE", "PPD"):
            self.add_error("metodo_pago_default", ValidationError("Método de pago inválido. Usa PUE o PPD."))
        cleaned["metodo_pago_default"] = mp

        limite_credito = cleaned.get("limite_credito")
        dias_credito = cleaned.get("dias_credito")
        if limite_credito is not None and limite_credito < 0:
            self.add_error("limite_credito", ValidationError("El límite de crédito no puede ser negativo."))
        if dias_credito is not None and dias_credito < 0:
            self.add_error("dias_credito", ValidationError("Los días de crédito no pueden ser negativos."))

        # Los datos fiscales son opcionales, pero si se captura alguno se pide el bloque completo mínimo.
        fiscales = [
            cleaned.get("rfc"),
            cleaned.get("nombre_fiscal"),
            codigos_regimenes_fiscales(cleaned.get("regimen_fiscal")),
            cleaned.get("domicilio_fiscal_cp"),
        ]
        if any(fiscales) and not all(fiscales):
            raise ValidationError("Si capturas información fiscal, completa RFC, nombre fiscal, régimen fiscal y CP fiscal.")

        if not cleaned.get("nombre_fiscal"):
            cleaned["nombre_fiscal"] = cleaned.get("nombre_comercial") or "PÚBLICO GENERAL"
        return cleaned

# --- Fin Clientes ---

# --- Inicio Almacenes ---

class AlmacenForm(forms.ModelForm):
    class Meta:
        model = Almacen
        fields = [
            "codigo",
            "nombre",
            "tipo",
            "ubicacion",
            "es_activo",
            "permite_ventas",
            "permite_transferencias",
            "es_virtual_sistema",
            "es_arrendado", 
            "tipo_costo", 
            "costo_almacen", 
            "vencimiento_dias",
        ]
        widgets = {
            "codigo": forms.TextInput(attrs={"class": "form-control"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "ubicacion": forms.TextInput(attrs={"class": "form-control"}),

            "es_activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "permite_ventas": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "permite_transferencias": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "es_virtual_sistema": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "es_arrendado": forms.CheckboxInput(attrs={"class": "form-check-input"}),

            "tipo_costo": forms.Select(attrs={"class": "form-select"}),
            "costo_almacen": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "vencimiento_dias": forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
        }

    def clean(self):
        cleaned = super().clean()
        es_arrendado = cleaned.get("es_arrendado")

        if es_arrendado:
            # exigir
            if not cleaned.get("tipo_costo"):
                self.add_error("tipo_costo", "Selecciona el tipo de costo para un almacén arrendado.")
            if cleaned.get("costo_almacen") in (None, ""):
                self.add_error("costo_almacen", "Captura el costo del almacén (arrendado).")
            if cleaned.get("vencimiento_dias") in (None, ""):
                self.add_error("vencimiento_dias", "Captura el vencimiento en días (arrendado).")
        else:
            # si es propio, limpiar (guardar NULL)
            cleaned["tipo_costo"] = None
            cleaned["costo_almacen"] = None
            cleaned["vencimiento_dias"] = None

        return cleaned


# --- Fin Almacenes ---
