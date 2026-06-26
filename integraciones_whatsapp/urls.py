from django.urls import path, include
from . import views

app_name = "integraciones_whatsapp"

urlpatterns = [
    path("integraciones/whatsapp/", include("integraciones_whatsapp.urls")),
    path("webhook/", views.whatsapp_webhook, name="webhook"),
]