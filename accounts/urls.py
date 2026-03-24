from django.urls import path
from . import views
from . import user_admin_views as uav

urlpatterns = [
    # Configuración -> Usuarios (solo superusers)
    path("usuarios/", uav.users_list, name="users_list"),
    path("usuarios/nuevo/", uav.users_create, name="users_create"),
    path("usuarios/<int:pk>/editar/", uav.users_update, name="users_update"),
    path("usuarios/<int:pk>/toggle/", uav.users_toggle_active, name="users_toggle_active"),
]
