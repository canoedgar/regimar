from django.contrib.auth.decorators import login_required
from accounts.decorators import grupos_requeridos, permiso_requerido
from django.shortcuts import render, get_object_or_404
from catalogos.models import Proyecto


@permiso_requerido("catalogos.view_proyecto")
def proyectos_home(request):
    print("Hola")
    proyectos = Proyecto.objects.all().order_by("-fecha_actualizacion", "nombre")
    return render(request, "proyectos/proyectos_home.html", {"proyectos": proyectos})


@permiso_requerido("catalogos.view_proyecto")
def proyecto_detail(request, pk):
    proyecto = get_object_or_404(Proyecto, pk=pk)
    return render(request, "proyectos/proyecto_detail.html", {"proyecto": proyecto})
