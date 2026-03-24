from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from catalogos.models import Proyecto


@login_required
def proyectos_home(request):
    print("Hola")
    proyectos = Proyecto.objects.all().order_by("-fecha_actualizacion", "nombre")
    return render(request, "proyectos/proyectos_home.html", {"proyectos": proyectos})


@login_required
def proyecto_detail(request, pk):
    proyecto = get_object_or_404(Proyecto, pk=pk)
    return render(request, "proyectos/proyecto_detail.html", {"proyecto": proyecto})
