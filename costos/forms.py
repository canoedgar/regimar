from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from catalogos.models import Almacen, Proveedor
from inventarios.models import EntradaInventario

from .models import CategoriaGasto, CierreCosteoPeriodo, Gasto, normalizar_nombre


class CategoriaGastoForm(forms.ModelForm):
    class Meta:
        model = CategoriaGasto
        fields = [
            "nombre",
            "tipo",
            "distribuible",
            "metodo_default_distribucion",
            "descripcion",
            "activo",
        ]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej. Flete de compra"}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "distribuible": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "metodo_default_distribucion": forms.Select(attrs={"class": "form-select"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Describe cuándo debe usarse esta categoría."}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "nombre": "Nombre de la categoría",
            "tipo": "Tipo de gasto",
            "distribuible": "Afecta costeo de productos",
            "metodo_default_distribucion": "Método default de distribución",
            "descripcion": "Descripción",
            "activo": "Categoría activa",
        }

    def clean_nombre(self):
        nombre = (self.cleaned_data.get("nombre") or "").strip()
        if not nombre:
            raise ValidationError("Captura el nombre de la categoría.")

        nombre_normalizado = normalizar_nombre(nombre)
        qs = CategoriaGasto.objects.filter(nombre_normalizado=nombre_normalizado)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Ya existe una categoría de gasto con un nombre equivalente.")
        return nombre

    def clean(self):
        cleaned_data = super().clean()
        distribuible = cleaned_data.get("distribuible")
        metodo = cleaned_data.get("metodo_default_distribucion")

        if not distribuible:
            cleaned_data["metodo_default_distribucion"] = CategoriaGasto.DIST_NO_DISTRIBUIR
        elif metodo == CategoriaGasto.DIST_NO_DISTRIBUIR:
            self.add_error(
                "metodo_default_distribucion",
                "Selecciona un método de distribución cuando la categoría afecta el costeo.",
            )

        return cleaned_data


class GastoForm(forms.ModelForm):
    class Meta:
        model = Gasto
        fields = [
            "fecha",
            "periodo_inicio",
            "periodo_fin",
            "categoria",
            "metodo_distribucion",
            "importe",
            "proveedor",
            "entrada_inventario",
            "almacen",
            "referencia",
            "descripcion",
            "observaciones",
        ]
        widgets = {
            "fecha": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "periodo_inicio": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "periodo_fin": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "categoria": forms.Select(attrs={"class": "form-select", "data-metodo-target": "categoria"}),
            "metodo_distribucion": forms.Select(attrs={"class": "form-select"}),
            "importe": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01", "placeholder": "0.00"}),
            "proveedor": forms.Select(attrs={"class": "form-select"}),
            "entrada_inventario": forms.Select(attrs={"class": "form-select"}),
            "almacen": forms.Select(attrs={"class": "form-select"}),
            "referencia": forms.TextInput(attrs={"class": "form-control", "placeholder": "Factura, recibo, transferencia o nota"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Describe el gasto capturado."}),
            "observaciones": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Notas internas opcionales."}),
        }
        labels = {
            "fecha": "Fecha del gasto",
            "periodo_inicio": "Periodo inicio",
            "periodo_fin": "Periodo fin",
            "categoria": "Categoría",
            "metodo_distribucion": "Método de distribución",
            "importe": "Importe",
            "proveedor": "Proveedor",
            "entrada_inventario": "Entrada relacionada",
            "almacen": "Almacén",
            "referencia": "Referencia",
            "descripcion": "Descripción",
            "observaciones": "Observaciones",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoy = timezone.localdate()

        self.fields["fecha"].input_formats = ["%Y-%m-%d"]
        self.fields["periodo_inicio"].input_formats = ["%Y-%m-%d"]
        self.fields["periodo_fin"].input_formats = ["%Y-%m-%d"]

        if not self.instance.pk:
            self.fields["fecha"].initial = hoy
            self.fields["periodo_inicio"].initial = hoy.replace(day=1)
            self.fields["periodo_fin"].initial = hoy

        categorias = CategoriaGasto.objects.filter(activo=True).order_by("tipo", "nombre")
        if self.instance.pk and self.instance.categoria_id:
            categorias = CategoriaGasto.objects.filter(pk=self.instance.categoria_id) | categorias
        self.fields["categoria"].queryset = categorias.distinct()
        self.fields["categoria"].empty_label = "Selecciona una categoría"

        self.fields["proveedor"].queryset = Proveedor.objects.filter(activo=True).order_by("nombre")
        self.fields["proveedor"].required = False
        self.fields["proveedor"].empty_label = "Sin proveedor"

        self.fields["entrada_inventario"].queryset = EntradaInventario.objects.select_related("proveedor", "almacen").order_by("-fecha", "-folio")
        self.fields["entrada_inventario"].required = False
        self.fields["entrada_inventario"].empty_label = "Sin entrada relacionada"

        self.fields["almacen"].queryset = Almacen.objects.filter(es_activo=True).order_by("nombre")
        self.fields["almacen"].required = False
        self.fields["almacen"].empty_label = "Sin almacén"

    def clean_categoria(self):
        categoria = self.cleaned_data.get("categoria")
        if not categoria:
            return categoria

        if not categoria.activo and not (self.instance.pk and self.instance.categoria_id == categoria.pk):
            raise ValidationError("Selecciona una categoría activa.")
        return categoria

    def clean_importe(self):
        importe = self.cleaned_data.get("importe")
        if importe is None:
            raise ValidationError("Captura el importe del gasto.")
        if importe <= 0:
            raise ValidationError("El importe debe ser mayor a 0.")
        return importe

    def clean(self):
        cleaned_data = super().clean()
        categoria = cleaned_data.get("categoria")
        metodo = cleaned_data.get("metodo_distribucion")
        periodo_inicio = cleaned_data.get("periodo_inicio")
        periodo_fin = cleaned_data.get("periodo_fin")
        entrada = cleaned_data.get("entrada_inventario")

        if self.instance.pk and not self.instance.puede_editarse:
            raise ValidationError("Solo se pueden editar gastos en borrador.")

        if periodo_inicio and periodo_fin and periodo_inicio > periodo_fin:
            self.add_error("periodo_fin", "La fecha final del periodo no puede ser menor a la fecha inicial.")

        if categoria:
            if not categoria.distribuible:
                cleaned_data["metodo_distribucion"] = CategoriaGasto.DIST_NO_DISTRIBUIR
            elif metodo == CategoriaGasto.DIST_NO_DISTRIBUIR:
                self.add_error("metodo_distribucion", "Selecciona un método de distribución para una categoría distribuible.")
            elif not metodo:
                cleaned_data["metodo_distribucion"] = categoria.metodo_default_distribucion

        if cleaned_data.get("metodo_distribucion") == CategoriaGasto.DIST_DIRECTO_ENTRADA and not entrada:
            self.add_error("entrada_inventario", "Selecciona la entrada relacionada cuando el método es directo a entrada.")

        return cleaned_data


class CierreCosteoPeriodoForm(forms.Form):
    periodo_inicio = forms.DateField(
        label="Periodo inicio",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
    )
    periodo_fin = forms.DateField(
        label="Periodo fin",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
    )
    notas = forms.CharField(
        label="Notas",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Notas internas del cierre."}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoy = timezone.localdate()
        if not self.is_bound:
            self.fields["periodo_inicio"].initial = hoy.replace(day=1)
            self.fields["periodo_fin"].initial = hoy

    def clean(self):
        cleaned_data = super().clean()
        periodo_inicio = cleaned_data.get("periodo_inicio")
        periodo_fin = cleaned_data.get("periodo_fin")

        if periodo_inicio and periodo_fin:
            if periodo_inicio > periodo_fin:
                self.add_error("periodo_fin", "La fecha final del periodo no puede ser menor a la fecha inicial.")
            else:
                cierre_vigente = (
                    CierreCosteoPeriodo.objects.filter(
                        periodo_inicio=periodo_inicio,
                        periodo_fin=periodo_fin,
                    )
                    .exclude(estado=CierreCosteoPeriodo.ESTADO_CANCELADO)
                    .exists()
                )
                if cierre_vigente:
                    self.add_error(None, "Ya existe un cierre de costeo vigente para el mismo periodo.")

        return cleaned_data
