from datetime import timedelta

from django import forms

from accounts.widgets import UniversalDateInput, UNIVERSAL_DATE_INPUT_FORMATS
from django.utils import timezone

from catalogos.models import Cliente, ParametroSistema
from .models import CotizacionPrecio


class CotizacionPrecioForm(forms.ModelForm):
    class Meta:
        model = CotizacionPrecio
        fields = ["cliente", "fecha", "fecha_vigencia", "observaciones"]
        widgets = {
            "cliente": forms.Select(attrs={"class": "form-select d-none"}),
            "fecha": UniversalDateInput(),
            "fecha_vigencia": UniversalDateInput(),
            "observaciones": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Condiciones comerciales u observaciones para esta cotización"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].queryset = Cliente.objects.all().order_by("nombre_fiscal")
        self.fields["cliente"].required = True
        self.fields["fecha"].required = True
        self.fields["fecha_vigencia"].required = True
        self.fields["fecha"].input_formats = UNIVERSAL_DATE_INPUT_FORMATS
        self.fields["fecha_vigencia"].input_formats = UNIVERSAL_DATE_INPUT_FORMATS

        if not self.instance.pk:
            hoy = timezone.localdate()
            dias = ParametroSistema.get_int("PRECIO_VIGENCIA_COTIZACIONES", 30)
            self.initial.setdefault("fecha", hoy)
            self.initial.setdefault("fecha_vigencia", hoy + timedelta(days=dias))
