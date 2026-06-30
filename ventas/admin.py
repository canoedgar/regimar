from django.contrib import admin

from .models import NotaVenta, NotaVentaDetalle


@admin.register(NotaVenta)
class NotaVentaAdmin(admin.ModelAdmin):
    list_display = ("folio", "fecha", "cliente_ref", "forma_pago_venta", "estado_pago", "estado")
    list_filter = ("estado", "estado_pago", "forma_pago_venta", "fecha")
    search_fields = ("folio", "cliente", "cliente_ref__nombre_fiscal", "cliente_ref__nombre_comercial")
    date_hierarchy = "fecha"


@admin.register(NotaVentaDetalle)
class NotaVentaDetalleAdmin(admin.ModelAdmin):
    list_display = ("salida", "producto", "cantidad", "precio_unitario", "costo_unitario_aplicado")
    list_filter = ("salida__fecha",)
    search_fields = ("salida__folio", "producto__nombre")

    def get_queryset(self, request):
        return super().get_queryset(request)
