from django.contrib import admin

from .models import ClienteSaldoFavorMovimiento, FacturaAplicacionNota, FacturaCliente, PagoAplicacionNota, PagoCliente, PagoMetodoDetalle


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


@admin.register(ClienteSaldoFavorMovimiento)
class ClienteSaldoFavorMovimientoAdmin(admin.ModelAdmin):
    list_display = ("cliente", "tipo", "fecha", "monto", "pago_origen", "nota_aplicada", "autorizado_por")
    list_filter = ("tipo", "fecha")
    search_fields = ("cliente__nombre_fiscal", "cliente__nombre_comercial", "referencia", "observaciones")

class FacturaAplicacionNotaInline(admin.TabularInline):
    model = FacturaAplicacionNota
    extra = 0
    readonly_fields = ("creado_en",)


@admin.register(FacturaCliente)
class FacturaClienteAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente", "folio_display", "tipo_aplicacion", "uuid", "fecha", "total", "total_xml", "estado", "creado_por")
    list_filter = ("estado", "tipo_aplicacion", "fecha", "tipo_comprobante", "moneda")
    search_fields = ("uuid", "serie", "folio", "cliente__nombre_fiscal", "cliente__nombre_comercial", "cliente__rfc", "rfc_receptor")
    readonly_fields = ("fecha_registro", "xml_hash", "cancelado_en", "total_xml")
    inlines = [FacturaAplicacionNotaInline]


@admin.register(FacturaAplicacionNota)
class FacturaAplicacionNotaAdmin(admin.ModelAdmin):
    list_display = ("factura", "nota_venta", "monto_facturado", "creado_en", "creado_por")
    search_fields = ("factura__uuid", "factura__folio", "nota_venta__folio", "factura__cliente__nombre_fiscal")

