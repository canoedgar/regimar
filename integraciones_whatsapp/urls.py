from django.urls import path

from . import views

app_name = "integraciones_whatsapp"

urlpatterns = [
    path("webhook/", views.whatsapp_webhook, name="webhook"),
    path("instrucciones/", views.instrucciones_list, name="instrucciones_list"),
    path("instrucciones/<int:pk>/", views.instruccion_detail, name="instruccion_detail"),
    path("remitentes/", views.remitentes_list, name="remitentes_list"),
    path("remitentes/nuevo/", views.remitente_create, name="remitente_create"),
    path("remitentes/<int:pk>/editar/", views.remitente_update, name="remitente_update"),
]
