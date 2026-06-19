from django.urls import path

from . import views

app_name = "cartera"

urlpatterns = [
    path("", views.cartera_dashboard, name="dashboard"),
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
