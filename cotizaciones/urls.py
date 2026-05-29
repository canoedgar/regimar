from django.urls import path

from . import views

app_name = "cotizaciones"

urlpatterns = [
    path("", views.cotizacion_list, name="cotizacion_list"),
    path("nueva/", views.cotizacion_create, name="cotizacion_create"),
    path("<int:pk>/", views.cotizacion_detail, name="cotizacion_detail"),
    path("<int:pk>/pdf/", views.cotizacion_pdf, name="cotizacion_pdf"),
    path("<int:pk>/aprobar/", views.cotizacion_aprobar, name="cotizacion_aprobar"),
    path("<int:pk>/cancelar/", views.cotizacion_cancelar, name="cotizacion_cancelar"),
]
