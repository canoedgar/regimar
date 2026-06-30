from django import forms

from accounts.widgets import UniversalDateInput, UNIVERSAL_DATE_INPUT_FORMATS
from catalogos.models import Cliente, Producto
from inventarios.models import SalidaInventario, SalidaInventarioDetalle
from ventas.models import NotaVenta


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


class SalidaVentaForm(forms.ModelForm):
    class Meta:
        model = SalidaInventario
        fields = [
            "folio",
            "fecha",
            "cliente_ref",
            "forma_pago_venta",
            "estado_pago",
            "cliente",
            "cliente_direccion",
            "cliente_contacto",
            "logo_nota",
            "documento_referencia",
            "motivo",
            "observaciones",
        ]
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
        self.fields["fecha"].input_formats = UNIVERSAL_DATE_INPUT_FORMATS
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

        if cleaned.get("forma_pago_venta") == SalidaInventario.FORMA_PAGO_TERMINAL:
            cleaned["estado_pago"] = SalidaInventario.ESTADO_PAGO_PAGADO

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
        model = NotaVenta
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
        self.fields["fecha"].input_formats = UNIVERSAL_DATE_INPUT_FORMATS
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
        if cleaned.get("forma_pago_venta") == NotaVenta.FORMA_PAGO_TERMINAL:
            cleaned["estado_pago"] = NotaVenta.ESTADO_PAGO_PAGADO
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
