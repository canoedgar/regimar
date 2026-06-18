# inventarios/urls.py
from django.urls import path
from .views import ajustes as v_ajustes, salidas as v_salidas, entradas as v_entradas, facturaentrada as v_factura, kardex as v_kardex, ventas as v_ventas, notas_edicion as v_notas_edicion, traspasos as v_traspasos
from catalogos.views import cliente_quick_create

urlpatterns = [
    path("entradas/", v_entradas.entradas_list, name="entradas_list"),    
    path("entradas/nueva/oc-factura/", v_factura.entrada_ocf_create, name="entrada_ocf_create"),
    path("entradas/nueva/manual/", v_entradas.entrada_manual_create, name="entrada_manual_create"),
    path("consultas/inventario_actual/", v_kardex.inventario_actual, name="inventario_actual"),
    path("ajustes/nuevo/", v_ajustes.ajuste_inventario, name="ajuste_inventario"),
    path("ajustes/stock-preview/", v_ajustes.ajuste_stock_preview, name="ajuste_stock_preview"),
    path("traspasos/nuevo/", v_traspasos.traspaso_inventario, name="traspaso_inventario"),
    path("traspasos/stock-preview/", v_traspasos.traspaso_stock_preview, name="traspaso_stock_preview"),
    path("ajustes/<str:tipo>/<int:pk>/deshacer/", v_ajustes.deshacer_ajuste, name="deshacer_ajuste"),
    path("entradas/<int:pk>/", v_entradas.entrada_detalle, name="entrada_detalle"),
    path("entradas/<int:pk>/deshacer-manual/", v_entradas.deshacer_entrada_manual, name="deshacer_entrada_manual"),
    path("salidas/", v_salidas.salidas_list, name="salidas_list"),
    path("kardex/", v_kardex.kardex, name="kardex"),
    path("kardex_export/", v_kardex.kardex_export, name="kardex_export"),    
    path("api/clientes/quick-create/", cliente_quick_create, name="cliente_quick_create"),
    path("salidas/<int:pk>/", v_salidas.salida_detalle, name="salida_detalle"),

    # View especializada para notas de venta
    path("ventas/", v_ventas.ventas_list, name="ventas_list"),
    path("ventas/notas/imprimir/", v_ventas.nota_venta_print, name="notas_venta_print_bulk"),
    path("ventas/notas/<int:pk>/imprimir/", v_ventas.nota_venta_print, name="nota_venta_print"),
    path("ventas/notas/<int:pk>/acciones/", v_notas_edicion.nota_venta_acciones, name="nota_venta_acciones"),
    path("ventas/notas/<int:pk>/editar/", v_notas_edicion.nota_venta_acciones, name="editar_nota_venta"),
    path("ventas/notas/<int:pk>/editar-datos/", v_notas_edicion.nota_venta_editar_datos, name="nota_venta_editar_datos"),
    path("ventas/notas/<int:pk>/ajustar-precios/", v_notas_edicion.nota_venta_ajustar_precios, name="nota_venta_ajustar_precios"),
    path("ventas/notas/<int:pk>/agregar-productos/", v_notas_edicion.nota_venta_agregar_productos, name="nota_venta_agregar_productos"),
    path("ventas/notas/<int:pk>/cancelar/", v_ventas.cancelar_nota_venta, name="cancelar_nota_venta"),
    path("salidas/venta/nueva/", v_salidas.salida_venta_create, name="salida_venta_create"),
    path("salidas/venta/precios-cliente/", v_salidas.precios_cliente_api, name="precios_cliente_api"),
    path("salidas/venta/autorizar-precio/<uuid:token>/", v_salidas.autorizar_precio_minimo, name="autorizar_precio_minimo"),

]