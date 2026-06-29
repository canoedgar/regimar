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

def _puede_editar_parametros_cartera(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or user.groups.filter(name=ADMIN_GROUP_NAME).exists())
    )


def _get_safe_next_url(request, default_url_name="clientes_list"):
    next_url = request.POST.get("next") or request.GET.get("next") or ""

    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure()
    ):
        return next_url

    return reverse(default_url_name)


def _add_cliente_to_next_url(next_url, cliente_id):
    """Devuelve al flujo origen conservando querystring y marcando el cliente recién creado."""
    parts = urlsplit(next_url)
    query_params = dict(parse_qsl(parts.query, keep_blank_values=True))
    query_params["cliente_id"] = str(cliente_id)
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(query_params),
        parts.fragment,
    ))


def _aplicar_datos_constancia_en_post(post_data, datos_constancia):
    """Mezcla datos extraídos de CSF en un POST mutable para re-renderizar el form."""
    data = post_data.copy()
    campos_cliente = [
        "tipo_persona",
        "rfc",
        "nombre_fiscal",
        "nombre_comercial",
        "domicilio_fiscal_cp",
        "calle",
        "num_ext",
        "num_int",
        "colonia",
        "localidad",
        "municipio",
        "estado",
        "pais",
        "cp",
        "referencias",
    ]

    regimenes = datos_constancia.get("regimenes_fiscales_codigos") or codigos_regimenes_fiscales(
        datos_constancia.get("regimen_fiscal")
    )
    if regimenes:
        data.setlist("regimen_fiscal", regimenes)

    for campo in campos_cliente:
        valor = (datos_constancia.get(campo) or "").strip()
        if valor:
            data[campo] = valor

    return data


def _leer_constancia_desde_request(request):
    archivo = request.FILES.get("constancia_situacion_fiscal_pdf")
    if not archivo:
        raise ConstanciaFiscalPDFError("Selecciona un PDF de constancia de situación fiscal para leerlo.")
    return extraer_datos_constancia_situacion_fiscal(archivo)


def _debe_abrir_datos_fiscales(form=None, forzar=False):
    if forzar:
        return True
    if not form or not getattr(form, "errors", None):
        return False

    campos_fiscales = {
        "tipo_persona",
        "rfc",
        "nombre_fiscal",
        "regimen_fiscal",
        "domicilio_fiscal_cp",
        "uso_cfdi_default",
        "email_cfdi",
        "constancia_situacion_fiscal_pdf",
    }
    return bool(campos_fiscales.intersection(form.errors.keys()) or form.non_field_errors())


def _mensaje_constancia_leida(request, datos_constancia):
    campos_importantes = [
        "rfc",
        "nombre_fiscal",
        "regimenes_fiscales_codigos",
        "domicilio_fiscal_cp",
        "calle",
        "colonia",
        "municipio",
        "estado",
    ]
    total = sum(1 for campo in campos_importantes if datos_constancia.get(campo))
    total_regimenes = len(datos_constancia.get("regimenes_fiscales_codigos") or [])
    detalle_regimenes = f" Se detectaron {total_regimenes} régimen(es) fiscal(es)." if total_regimenes else ""
    messages.success(
        request,
        f"Constancia leída correctamente. Se precargaron {total} campos; revisa la información antes de guardar.{detalle_regimenes}",
    )


@permiso_requerido("catalogos.view_cliente")
def clientes_list(request):
    q = (request.GET.get("q") or "").strip()

    clientes = Cliente.objects.all()
    if q:
        clientes = clientes.filter(
            Q(rfc__icontains=q) |
            Q(nombre_fiscal__icontains=q) |
            Q(nombre_comercial__icontains=q)
        )

    context = {
        "clientes": clientes,
        "q": q,
        "total": clientes.count(),
    }
    return render(request, "catalogos/clientes_list.html", context)


@permiso_requerido("catalogos.add_cliente")
def cliente_create(request):
    next_url = _get_safe_next_url(request)
    puede_editar_parametros_cartera = _puede_editar_parametros_cartera(request.user)
    abrir_datos_fiscales = False

    if request.method == "POST":
        accion = request.POST.get("accion") or "guardar"

        if accion == "extraer_constancia":
            data_form = request.POST
            abrir_datos_fiscales = True
            try:
                datos_constancia = _leer_constancia_desde_request(request)
                data_form = _aplicar_datos_constancia_en_post(request.POST, datos_constancia)
                _mensaje_constancia_leida(request, datos_constancia)
            except ConstanciaFiscalPDFError as exc:
                messages.error(request, str(exc))

            form = ClienteForm(
                data_form,
                request.FILES,
                puede_editar_parametros_cartera=puede_editar_parametros_cartera,
            )
        else:
            form = ClienteForm(
                request.POST,
                request.FILES,
                puede_editar_parametros_cartera=puede_editar_parametros_cartera,
            )
            if form.is_valid():
                try:
                    cliente = form.save()
                    messages.success(request, "Cliente creado correctamente.")
                    return redirect(_add_cliente_to_next_url(next_url, cliente.id))
                except IntegrityError:
                    form.add_error("rfc", "Ya existe un cliente con ese RFC.")
            abrir_datos_fiscales = _debe_abrir_datos_fiscales(form)
    else:
        form = ClienteForm(puede_editar_parametros_cartera=puede_editar_parametros_cartera)

    return render(request, "catalogos/cliente_form.html", {
        "form": form,
        "modo": "crear",
        "next_url": next_url,
        "puede_editar_parametros_cartera": puede_editar_parametros_cartera,
        "abrir_datos_fiscales": abrir_datos_fiscales,
    })

@permiso_requerido("catalogos.change_cliente")
def cliente_edit(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    puede_editar_parametros_cartera = _puede_editar_parametros_cartera(request.user)
    abrir_datos_fiscales = False

    if request.method == "POST":
        accion = request.POST.get("accion") or "guardar"

        if accion == "extraer_constancia":
            data_form = request.POST
            abrir_datos_fiscales = True
            try:
                datos_constancia = _leer_constancia_desde_request(request)
                data_form = _aplicar_datos_constancia_en_post(request.POST, datos_constancia)
                _mensaje_constancia_leida(request, datos_constancia)
            except ConstanciaFiscalPDFError as exc:
                messages.error(request, str(exc))

            form = ClienteForm(
                data_form,
                request.FILES,
                instance=cliente,
                puede_editar_parametros_cartera=puede_editar_parametros_cartera,
            )
        else:
            form = ClienteForm(
                request.POST,
                request.FILES,
                instance=cliente,
                puede_editar_parametros_cartera=puede_editar_parametros_cartera,
            )
            if form.is_valid():
                try:
                    form.save()
                    messages.success(request, "Cliente actualizado correctamente.")
                    return redirect("clientes_list")
                except IntegrityError:
                    form.add_error("rfc", "Ya existe un cliente con ese RFC.")
            abrir_datos_fiscales = _debe_abrir_datos_fiscales(form)
    else:
        form = ClienteForm(
            instance=cliente,
            puede_editar_parametros_cartera=puede_editar_parametros_cartera,
        )

    return render(request, "catalogos/cliente_form.html", {
        "form": form,
        "modo": "editar",
        "cliente": cliente,
        "puede_editar_parametros_cartera": puede_editar_parametros_cartera,
        "abrir_datos_fiscales": abrir_datos_fiscales,
    })


@permiso_requerido("catalogos.add_cliente")
@require_POST
def cliente_quick_create(request):
    try:
        rfc = (request.POST.get("rfc") or "").strip().upper()
        nombre_fiscal = (request.POST.get("nombre_fiscal") or "").strip()
        regimen_fiscal = (request.POST.get("regimen_fiscal") or "").strip()
        domicilio_fiscal_cp = (request.POST.get("domicilio_fiscal_cp") or "").strip()

        telefono = (request.POST.get("telefono") or "").strip()
        contacto = (request.POST.get("contacto") or "").strip()
        email_cfdi = (request.POST.get("email_cfdi") or "").strip()

        if not (rfc and nombre_fiscal and regimen_fiscal and domicilio_fiscal_cp):
            return JsonResponse({"ok": False, "error": "Faltan campos requeridos."}, status=400)

        c = Cliente(
            rfc=rfc,
            nombre_fiscal=nombre_fiscal,
            regimen_fiscal=regimen_fiscal_a_json([regimen_fiscal]),
            domicilio_fiscal_cp=domicilio_fiscal_cp,
            telefono=telefono,
            contacto=contacto,
            email_cfdi=email_cfdi,
        )

        c.full_clean()
        c.save()

        return JsonResponse({
            "ok": True,
            "id": c.id,
            "rfc": c.rfc,
            "nombre_fiscal": c.nombre_fiscal,
            "telefono": c.telefono,
            "contacto": c.contacto,
            "email_cfdi": c.email_cfdi,
        })

    except ValidationError as e:
        return JsonResponse({"ok": False, "error": "; ".join(sum(e.message_dict.values(), []))}, status=400)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


# --- Fin Clientes ---
