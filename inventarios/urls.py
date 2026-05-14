# inventarios/urls.py
from django.urls import path
from .views import ajustes as v_ajustes, salidas as v_salidas, entradas as v_entradas, facturaentrada as v_factura, kardex as v_kardex, ventas as v_ventas
from catalogos.views import cliente_quick_create

urlpatterns = [
    path("entradas/", v_entradas.entradas_list, name="entradas_list"),    
    path("entradas/nueva/oc-factura/", v_factura.entrada_ocf_create, name="entrada_ocf_create"),
    path("entradas/nueva/manual/", v_entradas.entrada_manual_create, name="entrada_manual_create"),
    path("consultas/inventario_actual/", v_kardex.inventario_actual, name="inventario_actual"),
    path("ajustes/nuevo/", v_ajustes.ajuste_inventario, name="ajuste_inventario"),
    path("entradas/<int:pk>/", v_entradas.entrada_detalle, name="entrada_detalle"),
    path("salidas/", v_salidas.salidas_list, name="salidas_list"),
    path("salidas/proyecto/nueva/", v_salidas.salida_proyecto_create, name="salida_proyecto_create"),
    path("kardex/", v_kardex.kardex, name="kardex"),
    path("kardex_export/", v_kardex.kardex_export, name="kardex_export"),    
    path("salidas/venta/nueva/", v_salidas.salida_venta_create, name="salida_venta_create"),
    path("api/clientes/quick-create/", cliente_quick_create, name="cliente_quick_create"),
    path("salidas/<int:pk>/", v_salidas.salida_detalle, name="salida_detalle"),

    # View especializada para notas de venta
    path("ventas/", v_ventas.ventas_list, name="ventas_list"),
    path("ventas/notas/imprimir/", v_ventas.nota_venta_print, name="notas_venta_print_bulk"),
    path("ventas/notas/<int:pk>/imprimir/", v_ventas.nota_venta_print, name="nota_venta_print"),
    path("ventas/notas/<int:pk>/cancelar/", v_ventas.cancelar_nota_venta, name="cancelar_nota_venta"),

]