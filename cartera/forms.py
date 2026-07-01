from decimal import Decimal

from django import forms
from django.utils import timezone

from accounts.widgets import UniversalDateInput, UNIVERSAL_DATE_INPUT_FORMATS

from catalogos.models import Cliente
from cartera.models import FacturaCliente, PagoMetodoDetalle
from ventas.models import NotaVenta


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

class FacturaClienteForm(ClienteBusquedaMixin, forms.Form):
    TIPO_APLICACION_CHOICES = FacturaCliente.TIPO_APLICACION_CHOICES

    xml = forms.FileField(
        label="XML de la factura",
        widget=forms.ClearableFileInput(attrs={"class": "form-control sg-form-control", "accept": ".xml,text/xml,application/xml"}),
        error_messages={"required": "Selecciona el XML de la factura."},
    )
    monto = forms.DecimalField(
        label="Monto de la factura",
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={
            "class": "form-control sg-form-control",
            "step": "0.01",
            "min": "0.01",
            "placeholder": "0.00",
            "inputmode": "decimal",
        }),
        help_text="Monto operativo que se usará en reportes. El XML se conserva íntegro sin modificarlo.",
    )
    tipo_aplicacion = forms.ChoiceField(
        label="Aplicación",
        choices=TIPO_APLICACION_CHOICES,
        initial=FacturaCliente.TIPO_GLOBAL,
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
        help_text="Global: solo queda relacionada al cliente. Aplicada a notas: se distribuye el monto entre una o varias notas.",
    )
    referencia = forms.CharField(
        label="Referencia interna",
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs={"class": "form-control sg-form-control", "placeholder": "Orden, folio interno o comentario corto"}),
    )
    observaciones = forms.CharField(
        label="Observaciones",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control sg-form-control", "rows": 3, "placeholder": "Comentarios internos de facturación"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.configurar_cliente_hidden()

    def clean_xml(self):
        xml = self.cleaned_data["xml"]
        if not xml.name.lower().endswith(".xml"):
            raise forms.ValidationError("El archivo debe tener extensión .xml.")
        max_size = 5 * 1024 * 1024
        if xml.size and xml.size > max_size:
            raise forms.ValidationError("El XML no debe exceder 5 MB.")
        return xml


class FacturaAplicacionNotaForm(forms.Form):
    nota_id = forms.ModelChoiceField(
        label="Nota",
        queryset=NotaVenta.objects.none(),
        required=False,
        empty_label="Selecciona una nota",
        widget=forms.Select(attrs={"class": "form-select sg-form-control"}),
    )
    monto = forms.DecimalField(
        label="Monto facturado",
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control sg-form-control", "step": "0.01", "min": "0.01", "placeholder": "0.00", "inputmode": "decimal"}),
    )
    observaciones = forms.CharField(
        label="Observaciones",
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control sg-form-control", "placeholder": "Opcional"}),
    )

    def __init__(self, *args, cliente=None, **kwargs):
        super().__init__(*args, **kwargs)
        if cliente:
            notas = NotaVenta.objects.filter(cliente_ref=cliente, estado=NotaVenta.ESTADO_ACTIVA).order_by("-fecha", "-folio")
            self.fields["nota_id"].queryset = notas
            self.fields["nota_id"].label_from_instance = self._label_nota

    @staticmethod
    def _label_nota(nota):
        return f"{nota.folio} · {nota.fecha:%Y-%m-%d}"

    def clean(self):
        cleaned = super().clean()
        nota = cleaned.get("nota_id")
        monto = cleaned.get("monto")
        if nota and not monto:
            self.add_error("monto", "Captura el monto facturado para la nota.")
        if monto and not nota:
            self.add_error("nota_id", "Selecciona la nota relacionada.")
        return cleaned


FacturaAplicacionNotaFormSet = forms.formset_factory(FacturaAplicacionNotaForm, extra=8, can_delete=False)


class CancelarFacturaForm(forms.Form):
    motivo_cancelacion = forms.CharField(
        label="Motivo de cancelación interna",
        required=True,
        min_length=8,
        widget=forms.Textarea(attrs={"class": "form-control sg-form-control", "rows": 3, "placeholder": "Describe por qué se cancela internamente esta factura."}),
        error_messages={
            "required": "Captura el motivo de cancelación interna.",
            "min_length": "El motivo debe tener al menos 8 caracteres.",
        },
    )

    def clean_motivo_cancelacion(self):
        return (self.cleaned_data.get("motivo_cancelacion") or "").strip()


class ReporteFacturacionForm(forms.Form):
    ESTADO_CHOICES = [("", "Todas"), *FacturaCliente.ESTADO_CHOICES]
    TIPO_CHOICES = [("", "Todos"), *FacturaCliente.TIPO_APLICACION_CHOICES]

    q = forms.CharField(label="Cliente o RFC", required=False, widget=forms.TextInput(attrs={"class": "form-control sg-form-control", "placeholder": "Cliente, RFC, receptor o UUID"}))
    fecha_inicio = forms.DateField(label="Desde", required=False, widget=UniversalDateInput(), input_formats=UNIVERSAL_DATE_INPUT_FORMATS)
    fecha_fin = forms.DateField(label="Hasta", required=False, widget=UniversalDateInput(), input_formats=UNIVERSAL_DATE_INPUT_FORMATS)
    estado = forms.ChoiceField(label="Estado", required=False, choices=ESTADO_CHOICES, widget=forms.Select(attrs={"class": "form-select sg-form-control"}))
    tipo_aplicacion = forms.ChoiceField(label="Aplicación", required=False, choices=TIPO_CHOICES, widget=forms.Select(attrs={"class": "form-select sg-form-control"}))

