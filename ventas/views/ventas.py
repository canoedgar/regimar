from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import permiso_requerido
from ventas.models import NotaVenta
from ventas.selectors.ventas import get_ventas_list_context
from ventas.services.cancelacion import CancelarNotaVentaService
from ventas.services.impresion import get_contexto_impresion_notas


@permiso_requerido("ventas.view_notaventa")
def ventas_list(request):
    return render(
        request,
        "ventas/ventas_list.html",
        get_ventas_list_context(request),
    )



@permiso_requerido("ventas.view_notaventa")
def nota_venta_print(request, pk=None):
    """Formato imprimible para una o varias notas."""
    return render(
        request,
        "ventas/nota_venta_print.html",
        get_contexto_impresion_notas(
            pk=pk,
            raw_ids=(request.GET.get("ids") or "").strip(),
        ),
    )


@permiso_requerido("ventas.change_notaventa")
@transaction.atomic
@require_POST
def cancelar_nota_venta(request, pk):
    nota = get_object_or_404(
        NotaVenta.objects.select_for_update().select_related("salida").prefetch_related(
            "salida__detalles__asignaciones__almacen",
            "salida__detalles__producto",
        ),
        pk=pk,
    )

    service = CancelarNotaVentaService(
        salida=nota,
        motivo=request.POST.get("motivo_cancelacion"),
    )
    errores = service.validar()

    if nota.estado == NotaVenta.ESTADO_CANCELADA:
        messages.warning(request, errores[0] if errores else f"La nota {nota.folio} ya se encontraba cancelada.")
        return redirect("ventas_list")

    if errores:
        for error in errores:
            messages.error(request, error)
        return redirect("ventas_list")

    service.execute()
    messages.success(request, f"Nota {nota.folio} cancelada. El inventario fue retornado correctamente.")
    return redirect("ventas_list")
