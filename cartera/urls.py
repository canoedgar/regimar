from django.urls import path

from . import views

app_name = "cartera"

urlpatterns = [
    path("", views.cartera_dashboard, name="dashboard"),
    path("facturas/", views.factura_list, name="factura_list"),
    path("facturas/nueva/", views.factura_create, name="factura_create"),
    path("facturas/nota/<int:nota_id>/nueva/", views.factura_create_desde_nota, name="factura_create_desde_nota"),
    path("facturas/<int:factura_id>/", views.factura_detalle, name="factura_detalle"),
    path("facturas/<int:factura_id>/preview/", views.factura_preview_print, name="factura_preview_print"),
    path("facturas/<int:factura_id>/xml/", views.factura_xml_download, name="factura_xml_download"),
    path("facturas/<int:factura_id>/cancelar/", views.factura_cancelar, name="factura_cancelar"),
    path("clientes/<int:cliente_id>/facturacion/", views.facturacion_cliente_reporte, name="facturacion_cliente_reporte"),
    path("clientes/<int:cliente_id>/facturacion/imprimir/", views.facturacion_cliente_reporte_print, name="facturacion_cliente_reporte_print"),
    path("reportes/facturacion-clientes/", views.reporte_facturacion_clientes, name="reporte_facturacion_clientes"),
    path("reportes/facturacion-clientes/imprimir/", views.reporte_facturacion_clientes_print, name="reporte_facturacion_clientes_print"),
    path("pagos/global/", views.pago_global_create, name="pago_global_create"),
    path("pagos/nota/<int:nota_id>/", views.pago_nota_create, name="pago_nota_create"),
    path("pagos/<int:pago_id>/", views.pago_detalle, name="pago_detalle"),
    path("pagos/<int:pago_id>/cancelar/", views.pago_cancelar, name="pago_cancelar"),
    path("pagos/<int:pago_id>/imprimir/", views.pago_detalle_print, name="pago_detalle_print"),
    path("clientes/<int:cliente_id>/estado-cuenta/", views.estado_cuenta_cliente, name="estado_cuenta_cliente"),
    path("clientes/<int:cliente_id>/estado-cuenta/imprimir/", views.estado_cuenta_cliente_print, name="estado_cuenta_cliente_print"),
    path("clientes/<int:cliente_id>/saldo-favor/liquidar/", views.liquidar_saldo_favor, name="liquidar_saldo_favor"),
    path("clientes/<int:cliente_id>/saldo-favor/aplicar/", views.aplicar_saldo_favor, name="aplicar_saldo_favor"),
    path("reportes/cartera-general/", views.reporte_cartera_general, name="reporte_cartera_general"),
    path("reportes/cartera-general/imprimir/", views.reporte_cartera_general_print, name="reporte_cartera_general_print"),
    path("reportes/pagos-dia/", views.reporte_pagos_dia, name="reporte_pagos_dia"),
    path("reportes/pagos-dia/imprimir/", views.reporte_pagos_dia_print, name="reporte_pagos_dia_print"),
]
