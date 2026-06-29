# catalogos/views.py
from openpyxl import load_workbook
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.http import JsonResponse, HttpResponseForbidden

from django.core.exceptions import ValidationError

from django.shortcuts import render, redirect, get_object_or_404
from .models import Producto, Categoria, Proveedor, Proyecto, Cliente, Almacen, ParametroSistema, ClienteProductoPrecio
from .forms import ProductoForm, CategoriaForm, ProveedorForm, ProyectoForm, ClienteForm, AlmacenForm, ProductoMetricaConversionFormSet, ParametroSistemaForm, ClienteProductoPrecioForm
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test, login_required
from accounts.decorators import ADMIN_GROUP_NAME, administrador_requerido, grupos_requeridos, permiso_requerido

from django.db.models import Q
from django.db import IntegrityError
from django.views.decorators.http import require_POST

from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone

from catalogos.services.precios import (
    registrar_bitacora_precio_producto,
    registrar_historial_precio_producto,
)
from catalogos.services.constancia_situacion_fiscal import (
    ConstanciaFiscalPDFError,
    extraer_datos_constancia_situacion_fiscal,
)
from catalogos.services.regimenes_fiscales import codigos_regimenes_fiscales, regimen_fiscal_a_json

# Inicio Categorías

@permiso_requerido("catalogos.view_proyecto")
def proyectos_list(request):
    estado = request.GET.get("estado", "").strip()
    qs = Proyecto.objects.all().order_by("-fecha_actualizacion", "nombre")
    if estado:
        qs = qs.filter(estado=estado)

    return render(request, "catalogos/proyectos_list.html", {
        "proyectos": qs,
        "estado_actual": estado,
        "ESTADOS": Proyecto.Estado.choices,
    })


@permiso_requerido("catalogos.add_proyecto")
def proyectos_create(request):
    if request.method == "POST":
        form = ProyectoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Proyecto creado correctamente.")
            return redirect("proyectos_list")
    else:
        form = ProyectoForm()

    return render(request, "catalogos/proyectos_form.html", {
        "form": form,
        "modo_edicion": False,
    })


@permiso_requerido("catalogos.change_proyecto")
def proyectos_edit(request, pk):
    proyecto = get_object_or_404(Proyecto, pk=pk)

    if request.method == "POST":
        form = ProyectoForm(request.POST, instance=proyecto)
        if form.is_valid():
            form.save()
            messages.success(request, "Proyecto actualizado correctamente.")
            return redirect("proyectos_list")
    else:
        form = ProyectoForm(instance=proyecto)

    return render(request, "catalogos/proyectos_form.html", {
        "form": form,
        "modo_edicion": True,
        "proyecto": proyecto,
    })

# --- Fin Proyectos ---

