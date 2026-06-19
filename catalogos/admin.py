
from django.contrib import admin

from .models import (
    Categoria, Producto, ProductoMetricaConversion, Proveedor, Proyecto, Cliente, Almacen,
    ProductoPrecioBitacora, ProductoPrecioHistorial, ParametroSistema, ClienteProductoPrecio,
    PrecioMenorMinimoAutorizacion, ClienteCreditoAutorizacion,
)


class ProductoMetricaConversionInline(admin.TabularInline):
    model = ProductoMetricaConversion
    extra = 0
    fields = ("nombre", "unidad_origen", "cantidad_origen", "factor_conversion", "activo")


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "categoria", "metrica", "precio", "precio_minimo", "ultimo_costo_compra", "costo_promedio", "stock", "maneja_peso_variable")
    search_fields = ("nombre", "nombre_normalizado")
    list_filter = ("categoria", "maneja_peso_variable", "metrica")
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


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nombre_fiscal", "nombre_comercial", "rfc", "limite_credito", "dias_credito", "activo")
    search_fields = ("nombre_fiscal", "nombre_comercial", "rfc", "telefono", "contacto")
    list_filter = ("activo", "logo")

admin.site.register(Almacen)


@admin.register(ProductoPrecioBitacora)
class ProductoPrecioBitacoraAdmin(admin.ModelAdmin):
    list_display = ("fecha", "producto", "precio_venta", "precio_minimo", "ultimo_costo_compra", "costo_promedio", "stock_actual", "margen_estimado")
    list_filter = ("fecha",)
    search_fields = ("producto__nombre",)
    readonly_fields = ("creado_en", "actualizado_en")


@admin.register(ProductoPrecioHistorial)
class ProductoPrecioHistorialAdmin(admin.ModelAdmin):
    list_display = ("creado_en", "producto", "precio_anterior", "precio_nuevo", "precio_minimo_anterior", "precio_minimo_nuevo", "usuario")
    list_filter = ("creado_en",)
    search_fields = ("producto__nombre", "usuario__username")
    readonly_fields = ("creado_en",)


@admin.register(ParametroSistema)
class ParametroSistemaAdmin(admin.ModelAdmin):
    list_display = ("clave", "nombre", "valor", "activo", "actualizado_en")
    search_fields = ("clave", "nombre")
    list_filter = ("activo",)


@admin.register(ClienteProductoPrecio)
class ClienteProductoPrecioAdmin(admin.ModelAdmin):
    list_display = ("cliente", "producto", "ultimo_precio", "fecha_ultimo_precio", "actualizado_por")
    search_fields = ("cliente__nombre_fiscal", "cliente__nombre_comercial", "producto__nombre")
    list_filter = ("fecha_ultimo_precio",)


@admin.register(PrecioMenorMinimoAutorizacion)
class PrecioMenorMinimoAutorizacionAdmin(admin.ModelAdmin):
    list_display = ("cliente", "producto", "precio_minimo", "precio_solicitado", "creado_en", "expira_en", "usado_en")
    search_fields = ("cliente__nombre_fiscal", "cliente__nombre_comercial", "producto__nombre")
    readonly_fields = ("token", "creado_en", "usado_en")


@admin.register(ClienteCreditoAutorizacion)
class ClienteCreditoAutorizacionAdmin(admin.ModelAdmin):
    list_display = ("cliente", "estado", "fecha_solicitud", "total_venta", "saldo_proyectado", "limite_credito", "dias_credito", "usado_en")
    search_fields = ("cliente__nombre_fiscal", "cliente__nombre_comercial", "token")
    list_filter = ("estado", "fecha_solicitud")
    readonly_fields = ("token", "creado_en", "respondido_en", "usado_en")
