from django.contrib import messages
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.decorators import permiso_requerido
from catalogos.models import Almacen

from ..forms import TraspasoInventarioForm
from ..models import InventarioStock, EntradaInventario, SalidaInventario
from ..services.folios import next_folio_movimiento
from ..services.traspasos import TraspasoInventarioService
from ..utils import decimal_or_default as _decimal


def _initial_traspaso():
    return {
        "folio_salida": next_folio_movimiento(tipo=SalidaInventario.TIPO_TRASLADO_SALIDA, width=6),
        "folio_entrada": next_folio_movimiento(tipo=EntradaInventario.TIPO_TRASLADO, width=6),
        "fecha": timezone.localdate(),
    }


def _render_traspaso(request, form, status=200):
    almacenes = Almacen.objects.filter(es_activo=True, permite_transferencias=True).order_by("tipo", "nombre")
    return render(request, "inventarios/traspaso_inventario.html", {
        "form": form,
        "almacenes": almacenes,
    }, status=status)


@permiso_requerido(
    "inventarios.add_entradainventario",
    "inventarios.add_salidainventario",
    "inventarios.change_inventariostock",
    require_all=True,
)
def traspaso_inventario(request):
    if request.method == "GET":
        form = TraspasoInventarioForm(initial=_initial_traspaso())
        return _render_traspaso(request, form)

    form = TraspasoInventarioForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Revisa los datos del traspaso.")
        return _render_traspaso(request, form, status=400)

    try:
        resultado = TraspasoInventarioService(usuario=request.user).ejecutar(data=form.cleaned_data)
    except IntegrityError as exc:
        messages.error(request, f"No se pudo aplicar el traspaso: {exc}")
        return _render_traspaso(request, form, status=400)

    messages.success(
        request,
        f"Traspaso aplicado correctamente. Salida: {resultado.salida.folio} | Entrada: {resultado.entrada.folio}",
    )
    return redirect("traspaso_inventario")


@permiso_requerido("inventarios.view_inventariostock")
def traspaso_stock_preview(request):
    producto_id = (request.GET.get("producto_id") or "").strip()
    origen_id = (request.GET.get("almacen_origen_id") or "").strip()
    cantidad = _decimal(request.GET.get("cantidad"), default="0")

    if not producto_id.isdigit() or not origen_id.isdigit():
        return JsonResponse({"ok": False, "message": "Selecciona almacén origen y producto."})

    stock_row = InventarioStock.objects.filter(producto_id=producto_id, almacen_id=origen_id).first()
    disponible = _decimal(stock_row.cantidad if stock_row else 0)
    costo_promedio = _decimal(getattr(stock_row, "costo_promedio", 0) if stock_row else 0)
    resultante = disponible - cantidad
    permite = cantidad > 0 and resultante >= 0

    if cantidad <= 0:
        message = "Captura una cantidad mayor a 0 para calcular el traspaso."
    elif not permite:
        message = "El traspaso dejaría inventario negativo en el almacén origen."
    else:
        message = "El traspaso puede aplicarse con el stock disponible."

    return JsonResponse({
        "ok": True,
        "disponible": str(disponible),
        "resultante": str(resultante),
        "costo_promedio": str(costo_promedio),
        "permite": permite,
        "message": message,
    })
