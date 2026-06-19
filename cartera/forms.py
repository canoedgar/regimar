from django import forms
from django.utils import timezone

from accounts.widgets import UniversalDateInput, UNIVERSAL_DATE_INPUT_FORMATS

from catalogos.models import Cliente
from cartera.models import PagoMetodoDetalle


def fecha_pago_inicial():
    return timezone.localdate().isoformat()


class FechaPagoMixin(forms.Form):
    fecha_pago = forms.DateField(
        label="Fecha en que pagó el cliente",
        required=True,
        initial=fecha_pago_inicial,
        widget=UniversalDateInput(),
        input_formats=UNIVERSAL_DATE_INPUT_FORMATS,
        help_text="Diferente a la fecha en que se registra el movimiento en el sistema.",
    )


class ClienteBusquedaMixin:
    def configurar_cliente_hidden(self):
        self.fields["cliente"] = forms.ModelChoiceField(
            queryset=Cliente.objects.filter(activo=True).order_by("nombre_fiscal", "nombre_comercial", "id"),
            widget=forms.HiddenInput(),
        )


class PagoGlobalForm(FechaPagoMixin, ClienteBusquedaMixin):
    monto = forms.DecimalField(
        label="Monto recibido",
        max_digits=14,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
            "min": "0.01",
            "placeholder": "0.00",
            "inputmode": "decimal",
        }),
    )
    metodo = forms.ChoiceField(
        label="Método de pago",
        choices=PagoMetodoDetalle.METODO_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    referencia = forms.CharField(
        label="Referencia",
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Folio, autorización, transferencia, banco, etc.",
            "autocomplete": "off",
        }),
    )
    observaciones = forms.CharField(
        label="Observaciones",
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Comentarios internos del pago",
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.configurar_cliente_hidden()


class PagoNotaForm(FechaPagoMixin):
    monto = forms.DecimalField(
        label="Monto a aplicar",
        max_digits=14,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
            "min": "0.01",
            "placeholder": "0.00",
            "inputmode": "decimal",
        }),
    )
    metodo = forms.ChoiceField(
        label="Método de pago",
        choices=PagoMetodoDetalle.METODO_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    referencia = forms.CharField(
        label="Referencia",
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Referencia del pago",
            "autocomplete": "off",
        }),
    )
    observaciones = forms.CharField(
        label="Observaciones",
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Comentarios internos del pago",
        }),
    )


class SaldoFavorDevolucionForm(forms.Form):
    fecha_liquidacion = forms.DateField(
        label="Fecha de liquidación/devolución",
        required=True,
        initial=fecha_pago_inicial,
        widget=UniversalDateInput(),
        input_formats=UNIVERSAL_DATE_INPUT_FORMATS,
    )
    monto = forms.DecimalField(
        label="Monto a liquidar / devolver",
        max_digits=14,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
            "min": "0.01",
            "placeholder": "0.00",
            "inputmode": "decimal",
        }),
    )
    metodo = forms.ChoiceField(
        label="Método de devolución",
        choices=PagoMetodoDetalle.METODO_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    referencia = forms.CharField(
        label="Referencia",
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Transferencia, folio, autorización, etc.",
            "autocomplete": "off",
        }),
    )
    observaciones = forms.CharField(
        label="Motivo / observaciones",
        required=True,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Describe por qué se liquida el saldo a favor.",
        }),
    )


class SaldoFavorAplicacionForm(FechaPagoMixin):
    nota_id = forms.IntegerField(widget=forms.HiddenInput())
    monto = forms.DecimalField(
        label="Monto de saldo a favor a aplicar",
        max_digits=14,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
            "min": "0.01",
            "placeholder": "0.00",
            "inputmode": "decimal",
        }),
    )
    referencia = forms.CharField(
        label="Referencia",
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Referencia interna o autorización",
            "autocomplete": "off",
        }),
    )
    observaciones = forms.CharField(
        label="Motivo / observaciones",
        required=True,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Describe por qué se aplica el saldo a favor a esta nota.",
        }),
    )


class CancelarPagoForm(forms.Form):
    motivo_cancelacion = forms.CharField(
        label="Motivo de cancelación",
        required=True,
        min_length=8,
        widget=forms.Textarea(attrs={
            "class": "form-control sg-form-control",
            "rows": 3,
            "placeholder": "Describe el error de captura, fecha incorrecta u otro motivo de cancelación.",
        }),
        error_messages={
            "required": "Captura el motivo de cancelación.",
            "min_length": "El motivo debe tener al menos 8 caracteres.",
        },
    )

    def clean_motivo_cancelacion(self):
        return (self.cleaned_data.get("motivo_cancelacion") or "").strip()
