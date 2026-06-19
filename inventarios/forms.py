# inventarios/forms.py
from django import forms

from accounts.widgets import UniversalDateInput, UNIVERSAL_DATE_INPUT_FORMATS
from django.forms import inlineformset_factory, formset_factory
from catalogos.models import Producto, Categoria, Proveedor, Cliente, Almacen
from .models import EntradaInventario, EntradaInventarioDetalle
from .models import SalidaInventario, SalidaInventarioDetalle



# --- Entradas ---

# --- Inicio Entrdadas -> Entrada OCF ---

class EntradaOCFacturaUploadForm(forms.Form):
    xml_archivo = forms.FileField(
        label="Factura XML",
        required=True,
        widget=forms.ClearableFileInput(attrs={"class": "form-control"})
    )

class EntradaOCFacturaForm(forms.Form):
    folio = forms.CharField(
        label="Folio",
        widget=forms.TextInput(attrs={"class": "form-control"})
    )
    fecha = forms.DateField(
        label="Fecha",
        widget=UniversalDateInput(),
        input_formats=UNIVERSAL_DATE_INPUT_FORMATS,
    )
    proveedor = forms.CharField(
        label="Proveedor",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )
    uuid_factura = forms.CharField(
        label="UUID factura",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )
    observaciones = forms.CharField(
        label="Observaciones",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3})
    )
    xml_archivo = forms.FileField(
        label="Factura XML",
        required=True,
        widget=forms.ClearableFileInput(attrs={"class": "form-control"})
    )

class ConciliacionLineaForm(forms.Form):
    
    MOTIVO_EXCLUSION_CHOICES = [
    ("FLETE", "Flete"),
    ("SERVICIO", "Servicio"),
    ("INSTALACION", "Instalación / Mano de obra"),
    ("AJUSTE", "Ajuste / Redondeo"),
    ("SEGURO_ENVIO", "Seguro / Envío"),
    ("OTRO", "Otro"),
    ]

    excluir = forms.BooleanField(
        label="Excluir (no inventariable)",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
    )

    motivo_exclusion = forms.ChoiceField(
        label="Motivo exclusión",
        required=False,
        choices=[("", "-- Motivo --")] + MOTIVO_EXCLUSION_CHOICES,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"})
    )

    motivo_exclusion_otro = forms.CharField(
        label="Otro motivo",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Especifica el motivo"})
    )
    
    # Datos que vienen del XML (solo lectura en la UI)
    clave_sat_xml = forms.CharField(widget=forms.HiddenInput())
    descripcion_xml = forms.CharField(widget=forms.HiddenInput())
    cantidad_xml = forms.DecimalField(decimal_places=2, max_digits=12)
    valor_unitario_xml = forms.DecimalField(decimal_places=2, max_digits=12)

    # Conciliación con el catálogo
    producto = forms.ModelChoiceField(
        label="Producto en sistema",
        queryset=Producto.objects.all(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"})
    )

    crear_nuevo = forms.BooleanField(
        label="Crear como nuevo producto",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
    )

    categoria_nueva = forms.ModelChoiceField(
        label="Categoría",
        queryset=Categoria.objects.all(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"})
    )
    nombre_nuevo = forms.CharField(
        label="Nombre producto",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"})
    )
    metrica_nueva = forms.CharField(
        label="Métrica",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"})
    )
    precio_nuevo = forms.DecimalField(
        label="Precio venta",
        decimal_places=2,
        max_digits=12,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm"})
    )

    def clean(self):
        cleaned = super().clean()

        excluir = cleaned.get("excluir")
        producto = cleaned.get("producto")
        crear_nuevo = cleaned.get("crear_nuevo")

        # Si excluye, no se exige conciliación, pero sí motivo
        if excluir:
            motivo = (cleaned.get("motivo_exclusion") or "").strip()
            if not motivo:
                raise forms.ValidationError("Si excluyes un renglón, selecciona el motivo de exclusión.")
            if motivo == "OTRO":
                if not (cleaned.get("motivo_exclusion_otro") or "").strip():
                    raise forms.ValidationError("Captura el motivo cuando seleccionas 'Otro'.")
            # Limpieza defensiva para evitar ambigüedad
            cleaned["producto"] = None
            cleaned["crear_nuevo"] = False
            return cleaned

        # Si NO excluye, debe conciliar o crear producto
        if not producto and not crear_nuevo:
            raise forms.ValidationError("Debes seleccionar un producto, crear uno nuevo o excluir el renglón.")

        if crear_nuevo:
            if not cleaned.get("categoria_nueva") or not cleaned.get("nombre_nuevo"):
                raise forms.ValidationError("Para crear un nuevo producto debes capturar categoría y nombre.")

        return cleaned

ConciliacionFormSet = formset_factory(ConciliacionLineaForm, extra=0)

class EntradaOCFacturaDetalleForm(forms.ModelForm):
    class Meta:
        model = EntradaInventarioDetalle
        fields = ["producto", "cantidad", "costo_unitario"]
        widgets = {
            "producto": forms.Select(attrs={"class": "form-select"}),
            "cantidad": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "costo_unitario": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }


EntradaOCFacturaDetalleFormSet = inlineformset_factory(
    EntradaInventario,
    EntradaInventarioDetalle,
    form=EntradaOCFacturaDetalleForm,
    fields=["producto", "cantidad", "costo_unitario"],
    extra=3,         
    can_delete=False,
)

# --- Fin Entrada OCF ---

# --- Inicio Entradas manuales ---

class EntradaManualForm(forms.ModelForm):
    class Meta:
        model = EntradaInventario
        fields = [
            "folio",
            "fecha",
            "proveedor",
            "documento_referencia",
            "motivo",
            "observaciones",
        ]
        widgets = {
            "folio": forms.TextInput(attrs={"class": "form-control", "readonly": "readonly"}),
            "fecha": UniversalDateInput(),
            "proveedor": forms.Select(attrs={"class": "form-select", "id": "proveedorSelect"}),
            "documento_referencia": forms.TextInput(attrs={"class": "form-control"}),
            "motivo": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "observaciones": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fecha"].input_formats = ["%Y-%m-%d"]

        self.fields["proveedor"].queryset = Proveedor.objects.filter(activo=True).order_by("nombre")
        self.fields["proveedor"].empty_label = "-- Selecciona --"

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.tipo = EntradaInventario.TIPO_ENTRADA_MANUAL        
        obj.tiene_xml = False
        obj.uuid_factura = None
        obj.xml_contenido = ""
        if commit:
            obj.save()
        return obj


class EntradaManualDetalleForm(forms.ModelForm):
    class Meta:
        model = EntradaInventarioDetalle
        fields = ["producto", "cantidad", "costo_unitario"]
        widgets = {
            "producto": forms.Select(attrs={"class": "form-select"}),
            "cantidad": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
            "costo_unitario": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
        }


EntradaManualDetalleFormSet = inlineformset_factory(
    EntradaInventario,
    EntradaInventarioDetalle,
    form=EntradaManualDetalleForm,
    fields=["producto", "cantidad", "costo_unitario"],
    extra=6,
    can_delete=True,
)

# --- Fin entradas manuales ---

class AjusteInventarioForm(forms.Form):    
    TIPO_AJUSTE_POSITIVO = "POS"
    TIPO_AJUSTE_NEGATIVO = "NEG"

    TIPO_AJUSTE_CHOICES = [
        (TIPO_AJUSTE_POSITIVO, "Ajuste positivo (entrada)"),
        (TIPO_AJUSTE_NEGATIVO, "Ajuste negativo (salida)"),
    ]

    folio = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={"readonly": "readonly", "class": "form-control"})
    )

    fecha = forms.DateField(
        required=True,
        widget=UniversalDateInput(),
        input_formats=UNIVERSAL_DATE_INPUT_FORMATS, 
    )

    producto = forms.ModelChoiceField(
        queryset=Producto.objects.all(),
        required=True,
        widget=forms.Select(attrs={"class": "form-select"})
    )

    cantidad = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=0.01,
        required=True,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"})
    )

    precio_unitario = forms.DecimalField(
        label="Precio / costo unitario",
        max_digits=12,
        decimal_places=2,
        min_value=0,
        required=True,
        help_text="Para ajuste positivo es costo de entrada; para ajuste negativo es precio de salida/referencia.",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"})
    )

    tipo_ajuste = forms.ChoiceField(
        choices=TIPO_AJUSTE_CHOICES,
        required=True,
        widget=forms.Select(attrs={"class": "form-select"})
    )

    motivo = forms.CharField(
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )

    observaciones = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3})
    )



class TraspasoInventarioForm(forms.Form):
    folio_salida = forms.CharField(
        label="Folio salida",
        max_length=20,
        required=True,
        widget=forms.TextInput(attrs={"readonly": "readonly", "class": "form-control"}),
    )
    folio_entrada = forms.CharField(
        label="Folio entrada",
        max_length=20,
        required=True,
        widget=forms.TextInput(attrs={"readonly": "readonly", "class": "form-control"}),
    )
    fecha = forms.DateField(
        label="Fecha de aplicación",
        required=True,
        widget=UniversalDateInput(),
        input_formats=UNIVERSAL_DATE_INPUT_FORMATS,
    )
    almacen_origen = forms.ModelChoiceField(
        label="Almacén origen",
        queryset=Almacen.objects.none(),
        required=True,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_almacen_origen"}),
    )
    almacen_destino = forms.ModelChoiceField(
        label="Almacén destino",
        queryset=Almacen.objects.none(),
        required=True,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_almacen_destino"}),
    )
    producto = forms.ModelChoiceField(
        label="Producto",
        queryset=Producto.objects.none(),
        required=True,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_producto"}),
    )
    cantidad = forms.DecimalField(
        label="Cantidad a traspasar",
        max_digits=14,
        decimal_places=2,
        min_value=0.01,
        required=True,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01", "id": "id_cantidad"}),
    )
    motivo = forms.CharField(
        label="Motivo",
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    observaciones = forms.CharField(
        label="Observaciones",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        almacenes = Almacen.objects.filter(es_activo=True, permite_transferencias=True).order_by("tipo", "nombre")
        self.fields["almacen_origen"].queryset = almacenes
        self.fields["almacen_origen"].empty_label = "-- Selecciona origen --"
        self.fields["almacen_destino"].queryset = almacenes
        self.fields["almacen_destino"].empty_label = "-- Selecciona destino --"
        self.fields["producto"].queryset = Producto.objects.all().order_by("nombre")
        self.fields["producto"].empty_label = "-- Selecciona producto --"

    def clean(self):
        cleaned = super().clean()
        origen = cleaned.get("almacen_origen")
        destino = cleaned.get("almacen_destino")
        cantidad = cleaned.get("cantidad")

        if origen and destino and origen.pk == destino.pk:
            self.add_error("almacen_destino", "El almacén destino debe ser diferente al almacén origen.")

        if origen and not origen.permite_transferencias:
            self.add_error("almacen_origen", "El almacén origen no permite transferencias.")

        if destino and not destino.permite_transferencias:
            self.add_error("almacen_destino", "El almacén destino no permite transferencias.")

        if cantidad is not None and cantidad <= 0:
            self.add_error("cantidad", "La cantidad debe ser mayor a 0.")

        return cleaned

class SalidaProyectoForm(forms.ModelForm):
    class Meta:
        model = SalidaInventario
        fields = ["folio", "fecha", "proyecto", "documento_referencia", "motivo", "observaciones"]
        widgets = {
            "folio": forms.TextInput(attrs={"class": "form-control"}),
            "fecha": UniversalDateInput(),
            "proyecto": forms.Select(attrs={"class": "form-select"}),
            "documento_referencia": forms.TextInput(attrs={"class": "form-control"}),
            "motivo": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "observaciones": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fecha"].input_formats = ["%Y-%m-%d"]

        self.instance.tipo = SalidaInventario.TIPO_PROYECTO

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.tipo = SalidaInventario.TIPO_PROYECTO
        if commit:
            obj.save()
        return obj


class SalidaInventarioDetalleForm(forms.ModelForm):
    class Meta:
        model = SalidaInventarioDetalle
        fields = ["producto", "cantidad", "precio_unitario"]
        widgets = {
            "producto": forms.Select(attrs={"class": "form-select"}),
            "cantidad": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
            "precio_unitario": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)        
        self.fields["producto"].queryset = Producto.objects.all().order_by("nombre")

    def clean(self):
        cleaned = super().clean()
        
        if hasattr(self, "add_prefix") and hasattr(self, "prefix") and hasattr(self, "data"):            
            pass

        return cleaned

class SalidaVentaForm(forms.ModelForm):
    class Meta:
        model = SalidaInventario
        fields = ["folio", "fecha", "cliente_ref", "forma_pago_venta", "estado_pago", "cliente", "cliente_direccion", "cliente_contacto", "logo_nota", "documento_referencia", "motivo", "observaciones"]
        widgets = {
            "folio": forms.TextInput(attrs={"class": "form-control"}),
            "fecha": UniversalDateInput(),
            "cliente_ref": forms.Select(attrs={"class": "form-select"}),
            "forma_pago_venta": forms.Select(attrs={"class": "form-select"}),
            "estado_pago": forms.Select(attrs={"class": "form-select"}),
            "cliente": forms.TextInput(attrs={"class": "form-control"}),
            "cliente_direccion": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "cliente_contacto": forms.TextInput(attrs={"class": "form-control"}),
            "logo_nota": forms.Select(attrs={"class": "form-select"}),
            "documento_referencia": forms.TextInput(attrs={"class": "form-control"}),
            "motivo": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "observaciones": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fecha"].input_formats = ["%Y-%m-%d"]
        self.fields["cliente_ref"].queryset = Cliente.objects.filter(activo=True).order_by("nombre_fiscal", "nombre_comercial")
        self.fields["cliente_ref"].required = True
        self.fields["cliente_ref"].empty_label = "-- Selecciona un cliente --"
        self.fields["logo_nota"].required = True

        self.fields["forma_pago_venta"].required = True
        self.fields["forma_pago_venta"].choices = [("", "-- Selecciona --")] + list(SalidaInventario.FORMA_PAGO_CHOICES)
        if not self.is_bound and "forma_pago_venta" not in self.initial:
            self.initial["forma_pago_venta"] = ""

        self.fields["estado_pago"].required = True
        self.fields["estado_pago"].choices = [("", "-- Selecciona --")] + list(SalidaInventario.ESTADO_PAGO_CHOICES)
        if not self.is_bound and "estado_pago" not in self.initial:
            self.initial["estado_pago"] = SalidaInventario.ESTADO_PAGO_PENDIENTE

        self.instance.tipo = SalidaInventario.TIPO_VENTA

    def clean(self):
        cleaned = super().clean()

        if not cleaned.get("cliente_ref"):
            self.add_error("cliente_ref", "Selecciona un cliente del catálogo.")

        if not cleaned.get("forma_pago_venta"):
            self.add_error("forma_pago_venta", "Selecciona la forma de pago.")

        if not cleaned.get("estado_pago"):
            self.add_error("estado_pago", "Selecciona el estado de pago.")

        if not cleaned.get("logo_nota"):
            self.add_error("logo_nota", "Selecciona el logo de la nota.")

        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.tipo = SalidaInventario.TIPO_VENTA
        obj.proyecto = None  # por seguridad
        if commit:
            obj.save()
        return obj



class SalidaVentaEdicionForm(forms.ModelForm):
    """
    Edición administrativa de nota de venta.
    No incluye campos que cambien inventario: productos, cantidades, presentaciones o almacenes.
    """

    class Meta:
        model = SalidaInventario
        fields = [
            "fecha",
            "cliente_ref",
            "forma_pago_venta",
            "estado_pago",
            "cliente",
            "cliente_direccion",
            "cliente_contacto",
            "logo_nota",
            "observaciones",
        ]
        widgets = {
            "fecha": UniversalDateInput(),
            "cliente_ref": forms.Select(attrs={"class": "form-select"}),
            "forma_pago_venta": forms.Select(attrs={"class": "form-select"}),
            "estado_pago": forms.Select(attrs={"class": "form-select"}),
            "cliente": forms.TextInput(attrs={"class": "form-control"}),
            "cliente_direccion": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "cliente_contacto": forms.TextInput(attrs={"class": "form-control"}),
            "logo_nota": forms.Select(attrs={"class": "form-select"}),
            "observaciones": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fecha"].input_formats = ["%Y-%m-%d"]
        self.fields["cliente_ref"].queryset = Cliente.objects.filter(activo=True).order_by("nombre_fiscal", "nombre_comercial")
        self.fields["cliente_ref"].required = True
        self.fields["cliente_ref"].empty_label = "-- Selecciona un cliente --"
        self.fields["logo_nota"].required = True
        self.fields["forma_pago_venta"].required = True
        self.fields["estado_pago"].required = True

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("cliente_ref"):
            self.add_error("cliente_ref", "Selecciona un cliente del catálogo.")
        if not cleaned.get("forma_pago_venta"):
            self.add_error("forma_pago_venta", "Selecciona la forma de pago.")
        if not cleaned.get("estado_pago"):
            self.add_error("estado_pago", "Selecciona el estado de pago.")
        if not cleaned.get("logo_nota"):
            self.add_error("logo_nota", "Selecciona el logo de la nota.")
        return cleaned


class SalidaVentaDetallePrecioForm(forms.ModelForm):
    class Meta:
        model = SalidaInventarioDetalle
        fields = ["precio_unitario"]
        widgets = {
            "precio_unitario": forms.NumberInput(attrs={"class": "form-control form-control-sm text-end", "step": "0.01", "min": "0.01"}),
        }

    def clean_precio_unitario(self):
        precio = self.cleaned_data.get("precio_unitario")
        if precio is None or precio <= 0:
            raise forms.ValidationError("El precio debe ser mayor a 0.")
        return precio
