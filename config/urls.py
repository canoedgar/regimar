from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from accounts.views import home, logout_view

urlpatterns = [
    path("admin/", admin.site.urls),

    # Login
    path("login/", auth_views.LoginView.as_view(
        template_name="accounts/login.html"
    ), name="login"),

    # Logout
    path("logout/", logout_view, name="logout"),

    # Home
    path("", home, name="home"),

    #Cartera
    path("cartera/", include("cartera.urls")),

    # Catálogos
    path("catalogos/", include("catalogos.urls")),

    # Inventarios
    path("inventarios/", include("inventarios.urls")),

    # Cotizaciones
    path("cotizaciones/", include("cotizaciones.urls")),

    # Proyectos
    path("proyectos/", include("proyectos.urls")),

    # Usuarios
    path("config/", include("accounts.urls")),

]
