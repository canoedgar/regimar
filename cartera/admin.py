from django.contrib import admin

from .models import ClienteSaldoFavorMovimiento, PagoAplicacionNota, PagoCliente, PagoMetodoDetalle


class PagoMetodoDetalleInline(admin.TabularInline):
    model = PagoMetodoDetalle
    extra = 0


class PagoAplicacionNotaInline(admin.TabularInline):
    model = PagoAplicacionNota
    extra = 0
    readonly_fields = ("aplicado_en",)


@admin.register(PagoCliente)
class PagoClienteAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente", "fecha", "tipo_aplicacion", "monto_recibido", "estado", "creado_por")
    list_filter = ("estado", "tipo_aplicacion", "origen", "fecha")
    search_fields = ("cliente__nombre_fiscal", "cliente__nombre_comercial", "referencia")
    date_hierarchy = "fecha"
    inlines = [PagoMetodoDetalleInline, PagoAplicacionNotaInline]


@admin.register(PagoMetodoDetalle)
class PagoMetodoDetalleAdmin(admin.ModelAdmin):
    list_display = ("pago", "metodo", "monto", "referencia")
    list_filter = ("metodo",)
    search_fields = ("referencia", "pago__cliente__nombre_fiscal", "pago__cliente__nombre_comercial")


@admin.register(PagoAplicacionNota)
class PagoAplicacionNotaAdmin(admin.ModelAdmin):
    list_display = ("pago", "nota_venta", "monto_aplicado", "aplicado_en", "creado_por")
    search_fields = ("nota_venta__folio", "pago__cliente__nombre_fiscal", "pago__cliente__nombre_comercial")
    date_hierarchy = "aplicado_en"


@admin.register(ClienteSaldoFavorMovimiento)
class ClienteSaldoFavorMovimientoAdmin(admin.ModelAdmin):
    list_display = ("cliente", "tipo", "fecha", "monto", "pago_origen", "nota_aplicada", "autorizado_por")
    list_filter = ("tipo", "fecha")
    search_fields = ("cliente__nombre_fiscal", "cliente__nombre_comercial", "referencia", "observaciones")
    date_hierarchy = "fecha"
