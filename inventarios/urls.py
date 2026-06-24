# inventarios/urls.py
from django.urls import path
from .views import ajustes as v_ajustes, salidas as v_salidas, entradas as v_entradas, kardex as v_kardex, traspasos as v_traspasos
from catalogos.views import cliente_quick_create

urlpatterns = [
    path("entradas/", v_entradas.entradas_list, name="entradas_list"),    
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


]