import re

from django import forms
from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.widgets import UniversalDateInput, UNIVERSAL_DATE_INPUT_FORMATS


_DESTINATARIOS_SPLIT_RE = re.compile(r"[,;\n]+")


def separar_destinatarios(valor):
    return [correo.strip() for correo in _DESTINATARIOS_SPLIT_RE.split(valor or "") if correo.strip()]


class ReporteGeneralCorreoForm(forms.Form):
    fecha_inicio = forms.DateField(
        label="Fecha inicial",
        required=True,
        initial=timezone.localdate,
        widget=UniversalDateInput(attrs={"class": "form-control sg-form-control"}),
        input_formats=UNIVERSAL_DATE_INPUT_FORMATS,
    )
    fecha_fin = forms.DateField(
        label="Fecha final",
        required=True,
        initial=timezone.localdate,
        widget=UniversalDateInput(attrs={"class": "form-control sg-form-control"}),
        input_formats=UNIVERSAL_DATE_INPUT_FORMATS,
    )
    destinatarios = forms.CharField(
        label="Destinatarios",
        required=True,
        widget=forms.Textarea(attrs={
            "class": "form-control sg-form-control",
            "rows": 3,
            "placeholder": "correo@empresa.com, direccion@empresa.com",
        }),
        help_text="Puedes separar varios correos con coma, punto y coma o salto de línea.",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        destinatarios_default = ", ".join(getattr(settings, "NOTIFICACIONES_REPORTES_DESTINATARIOS", []) or [])
        if not destinatarios_default and user and getattr(user, "email", ""):
            destinatarios_default = user.email
        self.fields["destinatarios"].initial = destinatarios_default

    def clean(self):
        cleaned = super().clean()
        fecha_inicio = cleaned.get("fecha_inicio")
        fecha_fin = cleaned.get("fecha_fin")
        if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
            raise ValidationError("La fecha inicial no puede ser mayor que la fecha final.")
        return cleaned

    def clean_destinatarios(self):
        valor = self.cleaned_data.get("destinatarios", "")
        correos = separar_destinatarios(valor)
        if not correos:
            raise ValidationError("Captura al menos un destinatario.")
        for correo in correos:
            validate_email(correo)
        return ", ".join(correos)

    @property
    def destinatarios_lista(self):
        return separar_destinatarios(self.cleaned_data.get("destinatarios", ""))
