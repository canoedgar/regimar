from django.urls import path

from . import views

app_name = "notificaciones"

urlpatterns = [
    path("reportes/general/", views.reporte_general_correo, name="reporte_general_correo"),
]
