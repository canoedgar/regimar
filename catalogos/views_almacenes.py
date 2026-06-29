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

@permiso_requerido("catalogos.view_almacen")
def almacenes_list(request):
    q = (request.GET.get("q") or "").strip()

    almacenes = Almacen.objects.all().order_by("nombre")
    if q:
        almacenes = almacenes.filter(
            Q(codigo__icontains=q) |
            Q(nombre__icontains=q) |
            Q(tipo__icontains=q)
        )

    return render(request, "catalogos/almacenes_list.html", {
        "almacenes": almacenes,
        "q": q,
        "total": almacenes.count(),
    })


@permiso_requerido("catalogos.add_almacen")
def almacenes_create(request):
    if request.method == "POST":
        form = AlmacenForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Almacén creado correctamente.")
            return redirect("almacenes_list")
    else:
        form = AlmacenForm()

    return render(request, "catalogos/almacenes_form.html", {
        "form": form,
        "modo_edicion": False,
    })


@permiso_requerido("catalogos.change_almacen")
def almacenes_edit(request, pk):
    almacen = get_object_or_404(Almacen, pk=pk)

    if request.method == "POST":
        form = AlmacenForm(request.POST, instance=almacen)
        if form.is_valid():
            form.save()
            messages.success(request, "Almacén actualizado correctamente.")
            return redirect("almacenes_list")
    else:
        form = AlmacenForm(instance=almacen)

    return render(request, "catalogos/almacenes_form.html", {
        "form": form,
        "modo_edicion": True,
        "almacen": almacen,
    })


@permiso_requerido("catalogos.delete_almacen")
def almacenes_confirm_delete(request, pk):
    almacen = get_object_or_404(Almacen, pk=pk)

    if request.method == "POST":
        nombre = str(almacen)
        almacen.delete()
        messages.success(request, f"Almacén '{nombre}' eliminado correctamente.")
        return redirect("almacenes_list")

    return render(request, "catalogos/almacenes_confirm_delete.html", {
        "almacen": almacen,
    })

# --- Fin Almacenes ---

