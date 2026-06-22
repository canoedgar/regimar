from django.contrib import admin

from .models import CategoriaGasto, CierreCosteoPeriodo, CierreCosteoProducto, Gasto, GastoDistribucion


@admin.register(CategoriaGasto)
class CategoriaGastoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "tipo", "distribuible", "metodo_default_distribucion", "activo")
    list_filter = ("tipo", "distribuible", "activo", "metodo_default_distribucion")
    search_fields = ("nombre", "nombre_normalizado", "descripcion")
    readonly_fields = ("nombre_normalizado", "creado_en", "actualizado_en")


class GastoDistribucionInline(admin.TabularInline):
    model = GastoDistribucion
    extra = 0
    can_delete = False
    readonly_fields = (
        "producto",
        "almacen",
        "metodo_distribucion",
        "cantidad_base",
        "porcentaje",
        "importe_asignado",
        "costo_unitario_asignado",
        "creado_en",
    )
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Gasto)
class GastoAdmin(admin.ModelAdmin):
    inlines = [GastoDistribucionInline]
    list_display = ("folio", "fecha", "categoria", "importe", "estado", "periodo_inicio", "periodo_fin")
    list_filter = ("estado", "categoria", "metodo_distribucion", "fecha", "periodo_inicio", "periodo_fin")
    search_fields = ("folio", "referencia", "descripcion", "observaciones", "proveedor__nombre", "entrada_inventario__folio")
    readonly_fields = (
        "folio",
        "estado",
        "creado_por",
        "aplicado_por",
        "cancelado_por",
        "aplicado_en",
        "cancelado_en",
        "creado_en",
        "actualizado_en",
    )



@admin.register(GastoDistribucion)
class GastoDistribucionAdmin(admin.ModelAdmin):
    list_display = ("gasto", "producto", "almacen", "metodo_distribucion", "cantidad_base", "importe_asignado")
    list_filter = ("metodo_distribucion", "gasto__estado", "almacen")
    search_fields = ("gasto__folio", "producto__nombre", "almacen__nombre")
    readonly_fields = (
        "gasto",
        "producto",
        "almacen",
        "entrada_detalle",
        "salida_detalle",
        "metodo_distribucion",
        "cantidad_base",
        "porcentaje",
        "importe_asignado",
        "costo_unitario_asignado",
        "creado_en",
    )


class CierreCosteoProductoInline(admin.TabularInline):
    model = CierreCosteoProducto
    extra = 0
    can_delete = False
    readonly_fields = (
        "producto",
        "cantidad_vendida",
        "venta_total",
        "costo_compra_total",
        "gasto_asignado_total",
        "costo_real_total",
        "utilidad_bruta",
        "utilidad_real",
        "margen_real_porcentaje",
    )
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CierreCosteoPeriodo)
class CierreCosteoPeriodoAdmin(admin.ModelAdmin):
    inlines = [CierreCosteoProductoInline]
    list_display = (
        "folio",
        "periodo_inicio",
        "periodo_fin",
        "estado",
        "total_ventas",
        "total_costo_real",
        "utilidad_real",
        "margen_real_porcentaje",
    )
    list_filter = ("estado", "periodo_inicio", "periodo_fin")
    search_fields = ("folio", "notas", "motivo_cancelacion")
    readonly_fields = (
        "folio",
        "estado",
        "total_productos",
        "total_movimientos_venta",
        "total_ventas",
        "total_costo_compra",
        "total_gastos_distribuidos",
        "total_costo_real",
        "utilidad_bruta",
        "utilidad_real",
        "margen_bruto_porcentaje",
        "margen_real_porcentaje",
        "creado_por",
        "cancelado_por",
        "creado_en",
        "cancelado_en",
        "actualizado_en",
    )


@admin.register(CierreCosteoProducto)
class CierreCosteoProductoAdmin(admin.ModelAdmin):
    list_display = (
        "cierre",
        "producto",
        "cantidad_vendida",
        "venta_total",
        "costo_real_total",
        "utilidad_real",
        "margen_real_porcentaje",
    )
    list_filter = ("cierre__estado", "cierre__periodo_inicio")
    search_fields = ("cierre__folio", "producto__nombre")
    readonly_fields = [field.name for field in CierreCosteoProducto._meta.fields]
