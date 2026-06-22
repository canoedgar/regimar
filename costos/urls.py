from django.urls import path

from . import views

app_name = "costos"

urlpatterns = [
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
