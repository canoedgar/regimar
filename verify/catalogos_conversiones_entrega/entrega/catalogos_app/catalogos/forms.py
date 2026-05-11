# catalogos/forms.py

#Productos
from django import forms
from django.forms import inlineformset_factory
from .models import Producto, Categoria, Proveedor, Proyecto, Cliente, Almacen, ProductoMetricaConversion

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

    # Campo de imagen SOLO en el formulario, no en el modelo
    imagen = forms.ImageField(
        required=False,
        widget=forms.ClearableFileInput(attrs={"class": "form-control"})
    )

    eliminar_imagen = forms.BooleanField(
        required=False, 
        label="Eliminar imagen", 
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
    )

    class Meta:
        model = Producto
        fields = [
            "categoria",
            "nombre",
            "clave_sat",
            "metrica",
            "precio",
            "stock",
            "stock_minimo",
            "stock_maximo",
            "es_equipo",                        
        ]
        widgets = {
            "categoria": forms.Select(attrs={"class": "form-select"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "clave_sat": forms.TextInput(attrs={"class": "form-control"}),
            "metrica": forms.TextInput(attrs={"class": "form-control"}),
            "precio": forms.NumberInput(attrs={"class": "form-control"}),
            "stock": forms.NumberInput(attrs={"class": "form-control"}),
            "stock_minimo": forms.NumberInput(attrs={"class": "form-control"}),
            "stock_maximo": forms.NumberInput(attrs={"class": "form-control"}),   
            "es_equipo": forms.CheckboxInput(attrs={"class": "form-cotrol"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Stock solo visible, no editable
        self.fields["stock"].disabled = True
        # Que se vea claramente de solo lectura
        self.fields["stock"].widget.attrs["readonly"] = True
        

    def save(self, commit=True):
        instance = super().save(commit=False)

        if self.cleaned_data.get("eliminar_imagen"):
            instance.imagen_base64 = None

        archivo_imagen = self.cleaned_data.get("imagen")
        if archivo_imagen:
            instance.imagen_base64 = imagen_a_base64_comprimida(archivo_imagen)

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
            "cantidad_origen": forms.NumberInput(attrs={"class": "form-control", "step": "0.0001", "min": "0.0001"}),
            "factor_conversion": forms.NumberInput(attrs={"class": "form-control", "step": "0.0001", "min": "0.0001"}),
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
    extra=2,
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
            "fecha_inicio": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d",),
            "fecha_fin": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d",),
        }

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

class ClienteForm(forms.ModelForm):
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
            "regimen_fiscal": forms.Select(attrs={"class": "form-select"}),
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

    def clean_rfc(self):
        rfc = (self.cleaned_data.get("rfc") or "").strip().upper()
        return rfc

    def clean(self):
        cleaned = super().clean()
        mp = (cleaned.get("metodo_pago_default") or "").strip().upper()
        if mp and mp not in ("PUE", "PPD"):
            self.add_error("metodo_pago_default", ValidationError("Método de pago inválido. Usa PUE o PPD."))
        cleaned["metodo_pago_default"] = mp
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
