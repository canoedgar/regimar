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

def _parametro_decimal(clave, default="0"):
    parametro = ParametroSistema.objects.filter(clave=clave, activo=True).first()
    if not parametro:
        return Decimal(str(default))
    try:
        return Decimal(str(parametro.valor))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(str(default))


def _redondear_cajas(value):
    return Decimal(value or 0).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _preparar_stock_cajas(producto, promedio_peso_variable):
    stock = Decimal(producto.stock or 0)
    factor = None

    if producto.maneja_peso_variable:
        factor = promedio_peso_variable
    else:
        conversiones = list(producto.conversiones_metricas.all())
        conversion = next((c for c in conversiones if c.activo), conversiones[0] if conversiones else None)
        if conversion:
            factor = conversion.factor_conversion

    if not factor or Decimal(factor) <= 0:
        producto.stock_cajas = None
        producto.stock_cajas_disponible = False
        return

    producto.stock_cajas = _redondear_cajas(stock / Decimal(factor))
    producto.stock_cajas_disponible = True


@permiso_requerido("catalogos.view_producto")
def productos_list(request):
    productos = Producto.objects.all().prefetch_related("conversiones_metricas").order_by("nombre")
    promedio_peso_variable = _parametro_decimal("ARRACHERA_PROM_CAJA", "0")

    for producto in productos:
        _preparar_stock_cajas(producto, promedio_peso_variable)

    return render(request, "catalogos/productos_list.html", {
        "productos": productos
    })


def _build_conversion_formset(request, producto=None):
    kwargs = {"instance": producto or Producto()}
    if request.method == "POST":
        kwargs.update({"data": request.POST, "files": request.FILES})
    formset = ProductoMetricaConversionFormSet(**kwargs)
    for form in formset.forms:
        form.producto = producto
    return formset


@permiso_requerido("catalogos.add_producto")
def productos_create(request):
    producto = Producto()

    if request.method == "POST":
        form = ProductoForm(request.POST, request.FILES, instance=producto)
        formset = _build_conversion_formset(request, producto)

        if form.is_valid() and formset.is_valid():
            producto = form.save()
            formset.instance = producto
            conversiones = formset.save(commit=False)
            for conversion in conversiones:
                conversion.producto = producto
                conversion.save()
            for eliminado in formset.deleted_objects:
                if eliminado.pk:
                    eliminado.delete()
            registrar_bitacora_precio_producto(
                producto,
                usuario=request.user,
                motivo="Alta de producto",
            )
            messages.success(request, "Producto creado correctamente.")
            return redirect("productos_list")
    else:
        form = ProductoForm(instance=producto)
        formset = _build_conversion_formset(request, producto)

    return render(request, "catalogos/productos_form.html", {
        "form": form,
        "formset_conversiones": formset,
        "producto": producto,
    })



@permiso_requerido("catalogos.change_producto")
def productos_edit(request, pk):
    producto = get_object_or_404(Producto, pk=pk)

    if request.method == "POST":
        precio_anterior = producto.precio
        precio_minimo_anterior = producto.precio_minimo

        form = ProductoForm(request.POST, request.FILES, instance=producto)
        formset = _build_conversion_formset(request, producto)
        if form.is_valid() and formset.is_valid():
            producto = form.save(commit=False)

            if producto.precio != precio_anterior:
                producto.fecha_ultima_actualizacion_precio = timezone.now()

            producto.save()

            registrar_historial_precio_producto(
                producto=producto,
                precio_anterior=precio_anterior,
                precio_nuevo=producto.precio,
                precio_minimo_anterior=precio_minimo_anterior,
                precio_minimo_nuevo=producto.precio_minimo,
                usuario=request.user,
                motivo="Actualización desde catálogo de productos",
            )
            registrar_bitacora_precio_producto(
                producto,
                usuario=request.user,
                motivo="Actualización desde catálogo de productos",
            )

            formset.instance = producto
            conversiones = formset.save(commit=False)
            for conversion in conversiones:
                conversion.producto = producto
                conversion.save()
            for eliminado in formset.deleted_objects:
                if eliminado.pk:
                    eliminado.delete()
            messages.success(request, "Producto actualizado correctamente.")
            return redirect("productos_list")
    else:
        form = ProductoForm(instance=producto)
        formset = _build_conversion_formset(request, producto)

    return render(request, "catalogos/productos_form.html", {
        "form": form,
        "formset_conversiones": formset,
        "producto": producto,
    })

@permiso_requerido("catalogos.delete_producto")
def productos_delete(request, pk):
    producto = get_object_or_404(Producto, pk=pk)

    if producto.stock != 0:
        messages.error(request, f"No se puede eliminar un producto '{producto.nombre}' porque su stock es {producto.stock}.")
        return redirect("productos_list")

    if request.method == "POST":
        nombre = producto.nombre
        producto.delete()        
        messages.success(request, f"Producto '{nombre}' eliminado correctamente.")
        return redirect("productos_list")

    return render(request, "catalogos/productos_confirm_delete.html", {
        "producto": producto,        
    })




@permiso_requerido("catalogos.view_producto", "catalogos.change_producto")
def precios_productos_list(request):
    productos = Producto.objects.all().order_by("nombre")

    if request.method == "POST":
        producto_id = request.POST.get("producto_id")
        producto = get_object_or_404(Producto, pk=producto_id)

        precio_anterior = producto.precio
        precio_minimo_anterior = producto.precio_minimo

        try:
            nuevo_precio = Decimal(str(request.POST.get("precio", "0") or "0"))
            nuevo_precio_minimo = Decimal(str(request.POST.get("precio_minimo", "0") or "0"))
        except (InvalidOperation, ValueError, TypeError):
            messages.error(request, "Precio inválido.")
            return redirect("precios_productos_list")

        if nuevo_precio < 0 or nuevo_precio_minimo < 0:
            messages.error(request, "Los precios no pueden ser negativos.")
            return redirect("precios_productos_list")

        producto.precio = nuevo_precio
        producto.precio_minimo = nuevo_precio_minimo
        producto.fecha_ultima_actualizacion_precio = timezone.now()
        producto.save(update_fields=["precio", "precio_minimo", "fecha_ultima_actualizacion_precio"])

        registrar_historial_precio_producto(
            producto=producto,
            precio_anterior=precio_anterior,
            precio_nuevo=producto.precio,
            precio_minimo_anterior=precio_minimo_anterior,
            precio_minimo_nuevo=producto.precio_minimo,
            usuario=request.user,
            motivo="Actualización desde lista maestra de precios",
        )
        registrar_bitacora_precio_producto(
            producto,
            usuario=request.user,
            motivo="Actualización desde lista maestra de precios",
        )

        messages.success(request, f"Precio de {producto.nombre} actualizado correctamente.")
        return redirect("precios_productos_list")

    return render(request, "catalogos/precios_productos_list.html", {
        "productos": productos,
    })


@permiso_requerido("catalogos.view_producto")
def producto_precio_bitacora(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    bitacora = producto.bitacora_precios.all()[:60]
    historial = producto.historial_precios.all()[:60]

    return render(request, "catalogos/producto_precio_bitacora.html", {
        "producto": producto,
        "bitacora": bitacora,
        "historial": historial,
    })


# --- Parámetros de sistema ---

def _es_admin(user):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name="Administrador").exists())


def _asegurar_parametros_base():
    ParametroSistema.objects.get_or_create(
        clave="PRECIO_VIGENCIA_DIAS",
        defaults={
            "nombre": "Días máximos de vigencia del último precio por cliente",
            "valor": "30",
            "descripcion": "Regla general para advertir cuando un cliente lleva demasiados días sin comprar un producto al último precio otorgado.",
            "activo": True,
        },
    )


@permiso_requerido("catalogos.view_parametrosistema")
def parametros_sistema_list(request):
    _asegurar_parametros_base()
    parametros = ParametroSistema.objects.all().order_by("clave")
    return render(request, "catalogos/parametros_sistema_list.html", {"parametros": parametros})


@permiso_requerido("catalogos.add_parametrosistema")
def parametros_sistema_create(request):
    form = ParametroSistemaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Parámetro creado correctamente.")
        return redirect("parametros_sistema_list")
    return render(request, "catalogos/parametros_sistema_form.html", {"form": form, "modo": "crear"})


@permiso_requerido("catalogos.change_parametrosistema")
def parametros_sistema_edit(request, pk):
    parametro = get_object_or_404(ParametroSistema, pk=pk)
    form = ParametroSistemaForm(request.POST or None, instance=parametro)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Parámetro actualizado correctamente.")
        return redirect("parametros_sistema_list")
    return render(request, "catalogos/parametros_sistema_form.html", {"form": form, "parametro": parametro, "modo": "editar"})


@permiso_requerido("catalogos.view_clienteproductoprecio")
def precios_clientes_list(request):
    precios = (
        ClienteProductoPrecio.objects
        .select_related("cliente", "producto", "actualizado_por")
        .order_by("cliente__nombre_fiscal", "producto__nombre")
    )
    q = (request.GET.get("q") or "").strip()
    if q:
        precios = precios.filter(
            Q(cliente__nombre_fiscal__icontains=q) |
            Q(cliente__nombre_comercial__icontains=q) |
            Q(producto__nombre__icontains=q)
        )
    return render(request, "catalogos/precios_clientes_list.html", {"precios": precios, "q": q})


@permiso_requerido("catalogos.change_clienteproductoprecio")
def precio_cliente_edit(request, pk):
    precio_cliente = get_object_or_404(ClienteProductoPrecio.objects.select_related("cliente", "producto"), pk=pk)
    precio_anterior = precio_cliente.ultimo_precio
    form = ClienteProductoPrecioForm(request.POST or None, instance=precio_cliente)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.precio_anterior = precio_anterior
