# accounts/views.py

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout


@login_required
def home(request):
    return render(request, "accounts/home.html")


def logout_view(request):
    """
    Cierra la sesión del usuario y lo redirige a la pantalla de login.
    """
    logout(request)
    return redirect("login")

def productos_list(request):
    return render(request, 'catalogos/productos_list.html')

def productos_form(request):
    return render(request, "catalogos/productos_form.html")
