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

@permiso_requerido("catalogos.view_proveedor")
def proveedores_list(request):
    proveedores = Proveedor.objects.all().order_by("nombre")
    return render(request, "catalogos/proveedores_list.html", {
        "proveedores": proveedores
    })

@permiso_requerido("catalogos.add_proveedor")
def proveedores_create(request):
    next_url = (request.GET.get("next") or "").strip()

    if request.method == "POST":
        form = ProveedorForm(request.POST)
        if form.is_valid():
            proveedor = form.save()
            messages.success(request, "Proveedor creado correctamente.")

            # ✅ Si venías de otra pantalla (ej. entrada manual), regresa y selecciona el proveedor
            if next_url:
                sep = "&" if "?" in next_url else "?"
                return redirect(f"{next_url}{sep}{urlencode({'proveedor_id': proveedor.id})}")

            return redirect("proveedores_list")
    else:
        form = ProveedorForm()

    return render(request, "catalogos/proveedores_form.html", {
        "form": form,
        "next": next_url,  # para que el template pueda usarlo en Cancelar
    })

@permiso_requerido("catalogos.change_proveedor")
def proveedores_edit(request, pk):
    proveedor = get_object_or_404(Proveedor, pk=pk)
    if request.method == "POST":
        form = ProveedorForm(request.POST, instance=proveedor)
        if form.is_valid():
            form.save()
            return redirect("proveedores_list")
    else:
        form = ProveedorForm(instance=proveedor)

    return render(request, "catalogos/proveedores_form.html", {
        "form": form,
        "proveedor": proveedor,
    })

# Fin Proveedores

