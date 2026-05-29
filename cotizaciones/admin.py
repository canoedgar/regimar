from django.contrib import admin

from .models import CotizacionPrecio, CotizacionPrecioDetalle


class CotizacionPrecioDetalleInline(admin.TabularInline):
    model = CotizacionPrecioDetalle
    extra = 0
    readonly_fields = ("costo_base", "precio_sugerido", "precio_minimo", "importe_estimado", "utilidad_total_estimada")


@admin.register(CotizacionPrecio)
class CotizacionPrecioAdmin(admin.ModelAdmin):
    list_display = ("folio", "cliente", "fecha", "fecha_vigencia", "estatus", "creado_por")
    list_filter = ("estatus", "fecha", "fecha_vigencia")
    search_fields = ("folio", "cliente__nombre_fiscal", "cliente__rfc")
    inlines = [CotizacionPrecioDetalleInline]


@admin.register(CotizacionPrecioDetalle)
class CotizacionPrecioDetalleAdmin(admin.ModelAdmin):
    list_display = ("cotizacion", "producto", "precio_propuesto", "margen_porcentaje", "utilidad_unitaria")
    search_fields = ("cotizacion__folio", "producto__nombre")
