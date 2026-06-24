from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from catalogos.models import Almacen, Proveedor
from inventarios.models import EntradaInventario

from .models import CategoriaGasto, CierreCosteoPeriodo, Gasto, GastoPeriodo, PeriodoCosteo, normalizar_nombre


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

class PeriodoCosteoForm(forms.ModelForm):
    class Meta:
        model = PeriodoCosteo
        fields = ["nombre", "fecha_inicio", "fecha_fin", "fecha_corte_almacen", "notas"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej. Junio 2026"}),
            "fecha_inicio": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "fecha_fin": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "fecha_corte_almacen": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "notas": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Notas internas del periodo."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoy = timezone.localdate()
        for field_name in ["fecha_inicio", "fecha_fin", "fecha_corte_almacen"]:
            self.fields[field_name].input_formats = ["%Y-%m-%d"]
        if not self.instance.pk and not self.is_bound:
            self.fields["fecha_inicio"].initial = hoy.replace(day=1)
            self.fields["fecha_fin"].initial = hoy
            self.fields["fecha_corte_almacen"].initial = hoy

    def clean(self):
        cleaned_data = super().clean()
        fecha_inicio = cleaned_data.get("fecha_inicio")
        fecha_fin = cleaned_data.get("fecha_fin")
        fecha_corte = cleaned_data.get("fecha_corte_almacen")

        if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
            self.add_error("fecha_fin", "La fecha final no puede ser menor a la fecha inicial.")
        if fecha_inicio and fecha_fin and fecha_corte:
            if fecha_corte < fecha_inicio or fecha_corte > fecha_fin:
                self.add_error("fecha_corte_almacen", "La fecha de corte debe estar dentro del periodo.")

        qs = PeriodoCosteo.objects.filter(fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if fecha_inicio and fecha_fin and qs.exists():
            self.add_error(None, "Ya existe un periodo de costeo con las mismas fechas.")

        return cleaned_data


class GastoPeriodoForm(forms.ModelForm):
    class Meta:
        model = GastoPeriodo
        fields = ["periodo", "tipo_gasto", "fecha", "importe", "almacen", "proveedor", "referencia", "descripcion"]
        widgets = {
            "periodo": forms.Select(attrs={"class": "form-select"}),
            "tipo_gasto": forms.Select(attrs={"class": "form-select"}),
            "fecha": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "importe": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01", "placeholder": "0.00"}),
            "almacen": forms.Select(attrs={"class": "form-select"}),
            "proveedor": forms.Select(attrs={"class": "form-select"}),
            "referencia": forms.TextInput(attrs={"class": "form-control", "placeholder": "Factura, recibo, transferencia o nota"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Describe el gasto capturado."}),
        }

    def __init__(self, *args, **kwargs):
        periodo = kwargs.pop("periodo", None)
        super().__init__(*args, **kwargs)
        hoy = timezone.localdate()
        self.fields["fecha"].input_formats = ["%Y-%m-%d"]
        self.fields["fecha"].initial = hoy

        periodos = PeriodoCosteo.objects.exclude(estado__in=[PeriodoCosteo.ESTADO_CERRADO, PeriodoCosteo.ESTADO_CANCELADO]).order_by("-fecha_inicio")
        if self.instance.pk and self.instance.periodo_id:
            periodos = PeriodoCosteo.objects.filter(pk=self.instance.periodo_id) | periodos
        self.fields["periodo"].queryset = periodos.distinct()
        self.fields["periodo"].empty_label = "Selecciona un periodo"

        if periodo:
            self.fields["periodo"].initial = periodo
            self.fields["fecha"].initial = periodo.fecha_fin

        self.fields["almacen"].queryset = Almacen.objects.filter(es_activo=True).order_by("nombre")
        self.fields["almacen"].required = False
        self.fields["almacen"].empty_label = "Sin almacén específico"

        self.fields["proveedor"].queryset = Proveedor.objects.filter(activo=True).order_by("nombre")
        self.fields["proveedor"].required = False
        self.fields["proveedor"].empty_label = "Sin proveedor"

    def clean_importe(self):
        importe = self.cleaned_data.get("importe")
        if importe is None or importe <= 0:
            raise ValidationError("El importe debe ser mayor a 0.")
        return importe

    def clean(self):
        cleaned_data = super().clean()
        periodo = cleaned_data.get("periodo")
        fecha = cleaned_data.get("fecha")
        if self.instance.pk and not self.instance.puede_editarse:
            raise ValidationError("Solo se pueden editar gastos activos de periodos abiertos o en revisión.")
        if periodo and fecha and (fecha < periodo.fecha_inicio or fecha > periodo.fecha_fin):
            self.add_error("fecha", "La fecha del gasto debe estar dentro del periodo seleccionado.")
        return cleaned_data

