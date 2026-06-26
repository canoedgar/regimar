from django import forms

from accounts.widgets import UniversalDateInput, UNIVERSAL_DATE_INPUT_FORMATS

from .models import WhatsAppInstruccion, WhatsAppRemitenteAutorizado
from .services.security_service import normalize_phone


class _BootstrapFormMixin:
    """Aplica clases Bootstrap/Sistema de Gestión a campos del formulario."""

    def _apply_bootstrap_classes(self):
        for field in self.fields.values():
            css_class = "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control sg-form-control"
            if isinstance(field.widget, forms.Select):
                css_class = "form-select sg-form-control"
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {css_class}".strip()


class WhatsAppInstruccionFiltroForm(_BootstrapFormMixin, forms.Form):
    """Filtros de la bandeja interna de instrucciones WhatsApp."""

    q = forms.CharField(
        label="Búsqueda",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Mensaje, remitente, teléfono o ID externo"}),
    )
    estado = forms.ChoiceField(
        label="Estado",
        required=False,
        choices=[("", "Todos")] + WhatsAppInstruccion.ESTADO_CHOICES,
    )
    telefono = forms.CharField(
        label="Teléfono",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "+526441277600"}),
    )
    tipo_mensaje = forms.CharField(
        label="Tipo de mensaje",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "text, image, interactive..."}),
    )
    fecha_desde = forms.DateField(
        label="Desde",
        required=False,
        input_formats=UNIVERSAL_DATE_INPUT_FORMATS,
        widget=UniversalDateInput(),
    )
    fecha_hasta = forms.DateField(
        label="Hasta",
        required=False,
        input_formats=UNIVERSAL_DATE_INPUT_FORMATS,
        widget=UniversalDateInput(),
    )
    con_error = forms.BooleanField(label="Solo con error", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap_classes()


class WhatsAppRemitenteFiltroForm(_BootstrapFormMixin, forms.Form):
    """Filtros del catálogo interno de remitentes autorizados."""

    ESTADO_CHOICES = [
        ("activos", "Activos"),
        ("inactivos", "Inactivos"),
        ("todos", "Todos"),
    ]

    q = forms.CharField(
        label="Búsqueda",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Nombre, teléfono, usuario o correo"}),
    )
    estado = forms.ChoiceField(label="Estado", required=False, choices=ESTADO_CHOICES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap_classes()


class WhatsAppRemitenteAutorizadoForm(_BootstrapFormMixin, forms.ModelForm):
    """Formulario controlado para administrar números autorizados."""

    class Meta:
        model = WhatsAppRemitenteAutorizado
        fields = [
            "telefono",
            "nombre",
            "usuario_sistema",
            "activo",
            "puede_consultar_stock",
            "puede_cambiar_precios",
            "puede_crear_clientes",
            "puede_registrar_inventario",
            "requiere_confirmacion_siempre",
        ]
        widgets = {
            "telefono": forms.TextInput(attrs={"placeholder": "+526441277600"}),
            "nombre": forms.TextInput(attrs={"placeholder": "Nombre del remitente autorizado"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap_classes()

    def clean_telefono(self):
        telefono = self.cleaned_data.get("telefono")
        telefono_normalizado = normalize_phone(telefono)
        if not telefono_normalizado:
            raise forms.ValidationError("Captura un teléfono válido.")
        return telefono_normalizado
