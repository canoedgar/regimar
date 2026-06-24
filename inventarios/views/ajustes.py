from django.contrib import messages
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import permiso_requerido
from catalogos.models import Almacen

from ..forms import AjusteInventarioForm
from ..selectors.ajustes import ajustes_recientes
from ..services.ajustes import AjusteInventarioService
from ..services.folios import next_folio_movimiento
from ..services.reversas import ReversaInventarioService
from ..utils import (
    build_productos_conversiones_json,
    decimal_or_default as _decimal,
    get_almacen_default,
    productos_con_conversiones_qs,
)


def _render_ajuste(request, form, almacenes_qs, almacen, status=200):
    productos = productos_con_conversiones_qs()
    return render(request, "inventarios/ajuste_inventario.html", {
        "form": form,
        "almacenes": almacenes_qs,
        "almacen": almacen,
        "ajustes_recientes": ajustes_recientes(limit=10),
        "productos_conversiones_json": build_productos_conversiones_json(productos),
        "conversion_id_actual": (request.POST.get("conversion_id") or "") if request.method == "POST" else "",
    }, status=status)


@permiso_requerido("inventarios.change_inventariostock")
def ajuste_inventario(request):
    almacenes_qs = Almacen.objects.filter(es_activo=True).order_by("tipo", "nombre")

    almacen = get_almacen_default()
    if not almacen:
        messages.error(request, "No hay almacenes activos. Crea al menos uno para operar inventario.")
        return redirect("almacenes_create")

    if request.method == "GET":
        form = AjusteInventarioForm(initial={
            "folio": next_folio_movimiento(tipo="AJU", width=6),
            "fecha": timezone.localdate(),
            "tipo_ajuste": AjusteInventarioForm.TIPO_AJUSTE_POSITIVO,
        })
        return _render_ajuste(request, form, almacenes_qs, almacen)

    almacen_id = (request.POST.get("almacen_id") or "").strip()
    if almacen_id.isdigit():
        almacen = almacenes_qs.filter(pk=int(almacen_id)).first() or almacen

    form = AjusteInventarioForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Revisa los datos del ajuste.")
        return _render_ajuste(request, form, almacenes_qs, almacen, status=400)

    try:
        resultado = AjusteInventarioService(usuario=request.user).aplicar(
            data=form.cleaned_data,
            almacen=almacen,
            conversion_id_raw=(request.POST.get("conversion_id") or "").strip(),
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return _render_ajuste(request, form, almacenes_qs, almacen, status=400)
    except IntegrityError as exc:
        messages.error(request, f"No se pudo aplicar el ajuste: {exc}")
        return _render_ajuste(request, form, almacenes_qs, almacen, status=400)

    messages.success(request, resultado.mensaje)
    return redirect("ajuste_inventario")


@permiso_requerido("inventarios.view_inventariostock")
def ajuste_stock_preview(request):
    service = AjusteInventarioService(usuario=request.user)
    data = service.preview(
        producto_id=(request.GET.get("producto_id") or "").strip(),
        almacen_id=(request.GET.get("almacen_id") or "").strip(),
        tipo_ajuste=(request.GET.get("tipo_ajuste") or "").strip(),
        cantidad_capturada=_decimal(request.GET.get("cantidad"), default="0"),
        conversion_id_raw=(request.GET.get("conversion_id") or "").strip(),
    )
    return JsonResponse(data)


@permiso_requerido("inventarios.change_inventariostock")
@require_POST
def deshacer_ajuste(request, tipo, pk):
    try:
        resultado = ReversaInventarioService(usuario=request.user).reversar_ajuste(
            tipo=tipo,
            movimiento_id=pk,
        )
    except ValueError as exc:
        messages.warning(request, str(exc))
        return redirect("ajuste_inventario")
    except IntegrityError as exc:
        messages.error(request, f"No se pudo deshacer el ajuste: {exc}")
        return redirect("ajuste_inventario")

    messages.success(request, resultado.mensaje)
    return redirect("ajuste_inventario")
