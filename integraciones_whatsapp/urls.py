from django.urls import path, include
from . import views

app_name = "integraciones_whatsapp"

urlpatterns = [    
    path("webhook/", views.whatsapp_webhook, name="webhook"),
]