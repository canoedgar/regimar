from django.urls import path
from . import views

urlpatterns = [
    path("", views.proyectos_home, name="proyectos_home"),
    path("<int:pk>/", views.proyecto_detail, name="proyecto_detail"),
]
