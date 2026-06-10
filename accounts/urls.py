from django.urls import path
from . import user_admin_views as uav

urlpatterns = [
    # Configuración -> Usuarios
    path("usuarios/", uav.users_list, name="users_list"),
    path("usuarios/nuevo/", uav.users_create, name="users_create"),
    path("usuarios/<int:pk>/editar/", uav.users_update, name="users_update"),
    path("usuarios/<int:pk>/toggle/", uav.users_toggle_active, name="users_toggle_active"),

    # Configuración -> Roles y permisos
    path("roles/", uav.roles_list, name="roles_list"),
    path("roles/nuevo/", uav.roles_create, name="roles_create"),
    path("roles/<int:pk>/editar/", uav.roles_update, name="roles_update"),
    path("roles/<int:pk>/eliminar/", uav.roles_delete, name="roles_delete"),
]
