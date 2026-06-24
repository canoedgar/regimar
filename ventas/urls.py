from django.urls import path

from ventas.views import notas_edicion as v_notas_edicion
from ventas.views import salidas as v_salidas
from ventas.views import ventas as v_ventas

urlpatterns = [
    path("", v_ventas.ventas_list, name="ventas_list"),
    path("nueva/", v_salidas.salida_venta_create, name="salida_venta_create"),
    path("precios-cliente/", v_salidas.precios_cliente_api, name="precios_cliente_api"),
    path("autorizar-precio/<uuid:token>/", v_salidas.autorizar_precio_minimo, name="autorizar_precio_minimo"),
    path("autorizacion-cartera/<str:token>/", v_salidas.autorizar_venta_extraordinaria, name="autorizar_venta_extraordinaria"),
    path("notas/imprimir/", v_ventas.nota_venta_print, name="notas_venta_print_bulk"),
    path("notas/<int:pk>/imprimir/", v_ventas.nota_venta_print, name="nota_venta_print"),
    path("notas/<int:pk>/acciones/", v_notas_edicion.nota_venta_acciones, name="nota_venta_acciones"),
    path("notas/<int:pk>/editar/", v_notas_edicion.nota_venta_acciones, name="editar_nota_venta"),
    path("notas/<int:pk>/editar-datos/", v_notas_edicion.nota_venta_editar_datos, name="nota_venta_editar_datos"),
    path("notas/<int:pk>/ajustar-precios/", v_notas_edicion.nota_venta_ajustar_precios, name="nota_venta_ajustar_precios"),
    path("notas/<int:pk>/agregar-productos/", v_notas_edicion.nota_venta_agregar_productos, name="nota_venta_agregar_productos"),
    path("notas/<int:pk>/cancelar/", v_ventas.cancelar_nota_venta, name="cancelar_nota_venta"),
]
