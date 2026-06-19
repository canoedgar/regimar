from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse

from accounts.decorators import permiso_requerido
from notificaciones.forms import ReporteGeneralCorreoForm
from notificaciones.services.reportes import construir_reporte_general, enviar_reporte_general_por_correo


@permiso_requerido(
    "notificaciones.puede_enviar_reportes",
    "notificaciones.add_notificacioncorreo",
)
def reporte_general_correo(request):
    if request.method == "POST":
        form = ReporteGeneralCorreoForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                enviar_reporte_general_por_correo(
                    fecha_inicio=form.cleaned_data["fecha_inicio"],
                    fecha_fin=form.cleaned_data["fecha_fin"],
                    destinatarios=form.destinatarios_lista,
                    usuario=request.user,
                )
                messages.success(request, "Reporte general enviado correctamente por correo.")
                return redirect(reverse("notificaciones:reporte_general_correo"))
            except Exception as exc:
                messages.error(request, f"No se pudo enviar el correo: {exc}")
    else:
        form = ReporteGeneralCorreoForm(user=request.user)

    reporte = None
    if not form.is_bound:
        reporte = construir_reporte_general()

    return render(request, "notificaciones/reporte_general_correo.html", {"form": form, "reporte": reporte})
