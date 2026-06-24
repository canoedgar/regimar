from django.urls import path

from . import views

app_name = "costos"

urlpatterns = [
    # Nuevo flujo simple de costos
    path("", views.costos_home, name="home"),
    path("periodos/", views.periodos_costeo_list, name="periodos_costeo_list"),
    path("periodos/nuevo/", views.periodo_costeo_create, name="periodo_costeo_create"),
    path("periodos/<int:pk>/", views.periodo_costeo_detail, name="periodo_costeo_detail"),
    path("periodos/<int:pk>/editar/", views.periodo_costeo_edit, name="periodo_costeo_edit"),
    path("periodos/<int:pk>/generar/", views.periodo_costeo_generar, name="periodo_costeo_generar"),
    path("periodos/<int:pk>/cerrar/", views.periodo_costeo_cerrar, name="periodo_costeo_cerrar"),
    path("periodos/<int:pk>/cancelar/", views.periodo_costeo_cancelar, name="periodo_costeo_cancelar"),
    path("gastos-periodo/", views.gastos_periodo_list, name="gastos_periodo_list"),
    path("gastos-periodo/nuevo/", views.gasto_periodo_create, name="gasto_periodo_create"),
    path("gastos-periodo/<int:pk>/editar/", views.gasto_periodo_edit, name="gasto_periodo_edit"),
    path("gastos-periodo/<int:pk>/cancelar/", views.gasto_periodo_cancelar, name="gasto_periodo_cancelar"),
    path("almacenaje/", views.almacenaje_costeo_list, name="almacenaje_costeo_list"),
    path("almacenaje/<int:pk>/", views.almacenaje_costeo_detail, name="almacenaje_costeo_detail"),
    path("resultados/", views.resultados_costeo_list, name="resultados_costeo_list"),
    path("resultados/<int:pk>/", views.resultados_costeo_detail, name="resultados_costeo_detail"),

    # Flujo anterior conservado como respaldo/configuración avanzada
    path("cierres/", views.cierres_costeo_list, name="cierres_costeo_list"),
    path("cierres/nuevo/", views.cierre_costeo_create, name="cierre_costeo_create"),
    path("cierres/<int:pk>/", views.cierre_costeo_detail, name="cierre_costeo_detail"),
    path("cierres/<int:pk>/cancelar/", views.cierre_costeo_cancelar, name="cierre_costeo_cancelar"),
    path("gastos/", views.gastos_list, name="gastos_list"),
    path("gastos/nuevo/", views.gasto_create, name="gasto_create"),
    path("gastos/<int:pk>/", views.gasto_detail, name="gasto_detail"),
    path("gastos/<int:pk>/editar/", views.gasto_edit, name="gasto_edit"),
    path("gastos/<int:pk>/aplicar/", views.gasto_aplicar, name="gasto_aplicar"),
    path("gastos/<int:pk>/cancelar/", views.gasto_cancelar, name="gasto_cancelar"),
    path("gastos/<int:pk>/recalcular-distribucion/", views.gasto_recalcular_distribucion, name="gasto_recalcular_distribucion"),
    path("categorias-gasto/", views.categorias_gasto_list, name="categorias_gasto_list"),
    path("categorias-gasto/nueva/", views.categoria_gasto_create, name="categoria_gasto_create"),
    path("categorias-gasto/<int:pk>/editar/", views.categoria_gasto_edit, name="categoria_gasto_edit"),
    path("categorias-gasto/<int:pk>/activar-desactivar/", views.categoria_gasto_toggle_activo, name="categoria_gasto_toggle_activo"),
]
