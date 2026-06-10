from django.contrib import messages
from django.contrib.auth.decorators import login_required
from accounts.decorators import grupos_requeridos, permiso_requerido
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import CotizacionPrecioForm
from .models import CotizacionPrecio
from .selectors import clientes_para_cotizacion, cotizaciones_listado, get_cotizacion_detalle, productos_para_cotizacion_ui
from .services import aprobar_cotizacion, cancelar_cotizacion, fecha_vigencia_default, guardar_cotizacion
from django.utils import timezone


@permiso_requerido("cotizaciones.view_cotizacionprecio")
def cotizacion_list(request):
    cotizaciones = list(cotizaciones_listado())
    for cotizacion in cotizaciones:
        cotizacion.marcar_vencida_si_aplica(guardar=True)
    return render(request, "cotizaciones/cotizacion_list.html", {"cotizaciones": cotizaciones})


@permiso_requerido("cotizaciones.add_cotizacionprecio")
def cotizacion_create(request):
    if request.method == "POST":
        form = CotizacionPrecioForm(request.POST)
        if form.is_valid():
            try:
                cotizacion = guardar_cotizacion(
                    form=form,
                    detalles_payload=request.POST.get("detalles_json", "[]"),
                    usuario=request.user,
                )
                messages.success(request, f"Cotización {cotizacion.folio} guardada correctamente.")
                detail_url = reverse("cotizaciones:cotizacion_detail", kwargs={"pk": cotizacion.pk})
                return redirect(f"{detail_url}?open_pdf=1")
            except ValueError as exc:
                messages.error(request, str(exc))
        else:
            messages.error(request, "Revisa los datos generales de la cotización.")
    else:
        form = CotizacionPrecioForm(initial={"fecha_vigencia": fecha_vigencia_default()})

    return render(request, "cotizaciones/cotizacion_form.html", _form_context(request, form=form))


@permiso_requerido("cotizaciones.view_cotizacionprecio")
def cotizacion_detail(request, pk):
    cotizacion = get_cotizacion_detalle(pk)
    cotizacion.marcar_vencida_si_aplica(guardar=True)
    return render(request, "cotizaciones/cotizacion_detail.html", {"cotizacion": cotizacion})


@permiso_requerido("cotizaciones.view_cotizacionprecio")
def cotizacion_pdf(request, pk):
    cotizacion = get_cotizacion_detalle(pk)
    cotizacion.marcar_vencida_si_aplica(guardar=True)
    return render(request, "cotizaciones/cotizacion_pdf.html", {"cotizacion": cotizacion})


@permiso_requerido("cotizaciones.change_cotizacionprecio")
def cotizacion_aprobar(request, pk):
    if request.method != "POST":
        return HttpResponseBadRequest("Método no permitido")
    cotizacion = get_object_or_404(CotizacionPrecio.objects.prefetch_related("detalles__producto"), pk=pk)
    try:
        aprobar_cotizacion(cotizacion=cotizacion, usuario=request.user)
        messages.success(request, "Cotización aprobada. Los precios quedaron guardados para el cliente.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("cotizaciones:cotizacion_detail", pk=pk)


@permiso_requerido("cotizaciones.change_cotizacionprecio")
def cotizacion_cancelar(request, pk):
    if request.method != "POST":
        return HttpResponseBadRequest("Método no permitido")
    cotizacion = get_object_or_404(CotizacionPrecio, pk=pk)
    try:
        cancelar_cotizacion(cotizacion=cotizacion)
        messages.success(request, "Cotización cancelada correctamente.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("cotizaciones:cotizacion_detail", pk=pk)


def _date_value(field, fallback):
    value = field.value()
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return value or fallback.strftime("%Y-%m-%d")


def _form_context(request, *, form):
    hoy = timezone.localdate()
    vigencia_default = fecha_vigencia_default()
    return {
        "form": form,
        "fecha_actual_value": _date_value(form["fecha"], hoy),
        "fecha_vigencia_value": _date_value(form["fecha_vigencia"], vigencia_default),
        "clientes": clientes_para_cotizacion(),
        "productos_ui": productos_para_cotizacion_ui(),
        "cliente_create_url": f"{reverse('cliente_create')}?next={request.get_full_path()}",
    }
