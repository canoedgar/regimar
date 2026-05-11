
from django.contrib import admin

from .models import Categoria, Producto, ProductoMetricaConversion, Proveedor, Proyecto, Cliente, Almacen


class ProductoMetricaConversionInline(admin.TabularInline):
    model = ProductoMetricaConversion
    extra = 0
    fields = ("nombre", "unidad_origen", "cantidad_origen", "factor_conversion", "activo")


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "categoria", "metrica", "precio", "stock", "es_equipo")
    search_fields = ("nombre", "clave_sat", "nombre_normalizado")
    list_filter = ("categoria", "es_equipo", "metrica")
    inlines = [ProductoMetricaConversionInline]


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nombre",)
    search_fields = ("nombre", "nombre_normalizado")


@admin.register(ProductoMetricaConversion)
class ProductoMetricaConversionAdmin(admin.ModelAdmin):
    list_display = ("producto", "nombre", "unidad_origen", "cantidad_origen", "factor_conversion", "activo")
    search_fields = ("producto__nombre", "nombre", "nombre_normalizado", "unidad_origen")
    list_filter = ("activo", "unidad_origen")


admin.site.register(Proveedor)
admin.site.register(Proyecto)
admin.site.register(Cliente)
admin.site.register(Almacen)
