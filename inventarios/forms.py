# inventarios/forms.py
from django import forms

from accounts.widgets import UniversalDateInput, UNIVERSAL_DATE_INPUT_FORMATS
from django.forms import inlineformset_factory
from catalogos.models import Producto, Proveedor, Cliente, Almacen
from .models import EntradaInventario, EntradaInventarioDetalle
from .models import SalidaInventario, SalidaInventarioDetalle



# --- Entradas ---

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
        self.fields["fecha"].input_formats = UNIVERSAL_DATE_INPUT_FORMATS

        self.fields["proveedor"].queryset = Proveedor.objects.filter(activo=True).order_by("nombre")
        self.fields["proveedor"].empty_label = "-- Selecciona --"

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.tipo = EntradaInventario.TIPO_ENTRADA_MANUAL        
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

