from django.contrib import admin
from .models import EntradaInventario, EntradaInventarioDetalle


class EntradaInventarioDetalleInline(admin.TabularInline):
    model = EntradaInventarioDetalle
    extra = 1


@admin.register(EntradaInventario)
class EntradaInventarioAdmin(admin.ModelAdmin):
    list_display = ("folio", "fecha", "tipo", "proveedor", "creado_en")
    list_filter = ("tipo", "fecha")
    search_fields = ("folio", "proveedor", "uuid_factura")
    inlines = [EntradaInventarioDetalleInline]
