from django.contrib import messages
from django.db import transaction
from django.forms import modelformset_factory
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import permiso_requerido
from catalogos.sat_catalogos import REGIMEN_FISCAL_CHOICES
from catalogos.services.credito_clientes import total_detalles_venta
from inventarios.models import SalidaInventario, SalidaInventarioDetalle
from inventarios.services.folios import next_folio_movimiento
from ventas.forms import SalidaInventarioDetalleForm, SalidaVentaForm
from ventas.selectors.ventas import get_contexto_salida_venta
from ventas.services.autorizaciones import (
    autorizar_precio_minimo_cliente,
    get_autorizacion_credito_queryset,
    get_autorizacion_precio_queryset,
    resolver_autorizacion_credito,
)
from ventas.services.creacion import VentaService
from ventas.services.impresion import get_nota_guardada_para_impresion
from ventas.services.precios_cliente import get_precios_cliente_payload
from ventas.services.venta_data import VentaOperacionData, VentaRequestContext
from ventas.services.venta_parser import VentaPostParser
from ventas.services.comisiones import calcular_total_con_comision, get_porcentaje_comision_terminal


@permiso_requerido("catalogos.view_clienteproductoprecio")
def precios_cliente_api(request):
    return JsonResponse(get_precios_cliente_payload(
        cliente_id=(request.GET.get("cliente_id") or "").strip(),
        producto_ids=request.GET.getlist("producto_id"),
    ))


@permiso_requerido("catalogos.change_preciomenorminimoautorizacion")
def autorizar_precio_minimo(request, token):
    autorizacion = get_object_or_404(get_autorizacion_precio_queryset(), token=token)
    ok, mensaje = autorizar_precio_minimo_cliente(
        autorizacion=autorizacion,
        usuario=request.user,
    )
    if ok:
        messages.success(request, mensaje)
        return redirect("precios_clientes_list")
    messages.error(request, mensaje)
    return redirect("home")


def autorizar_venta_extraordinaria(request, token):
    autorizacion = get_object_or_404(get_autorizacion_credito_queryset(), token=token)
    contexto = resolver_autorizacion_credito(
        autorizacion=autorizacion,
        accion=request.POST.get("accion") if request.method == "POST" else "",
        comentario=request.POST.get("comentario") if request.method == "POST" else "",
        es_post=request.method == "POST",
    )
    return render(request, "catalogos/autorizaciones/credito_resolver.html", contexto)


def _get_detalle_formset_factory(can_delete=True):
    return modelformset_factory(
        SalidaInventarioDetalle,
        form=SalidaInventarioDetalleForm,
        extra=0,
        can_delete=can_delete,
    )


def _get_form_venta_inicial():
    return SalidaVentaForm(initial={
        "folio": next_folio_movimiento(tipo="VTA", width=6),
        "fecha": timezone.localdate(),
        "forma_pago_venta": "",
        "estado_pago": SalidaInventario.ESTADO_PAGO_PENDIENTE,
    })


def _render_salida_venta_form(
    request,
    form,
    formset,
    productos_ui,
    clientes,
    almacenes_qs,
    almacen_default,
    nota_guardada=None,
):
    context = {
        "form": form,
        "formset": formset,
        "productos_ui": productos_ui,
        "clientes": clientes,
        "almacenes": almacenes_qs,
        "almacen": almacen_default,
        "REGIMEN_FISCAL_CHOICES": REGIMEN_FISCAL_CHOICES,
        "comision_terminal_porcentaje": get_porcentaje_comision_terminal(),
    }

    if nota_guardada is not None:
        context["nota_guardada"] = nota_guardada

    return render(request, "ventas/salida_venta_form.html", context)


def _render_salida_venta_desde_contexto(
    request,
    form,
    formset,
    contexto_venta,
    nota_guardada=None,
):
    return _render_salida_venta_form(
        request=request,
        form=form,
        formset=formset,
        productos_ui=contexto_venta["productos_ui"],
        clientes=contexto_venta["clientes"],
        almacenes_qs=contexto_venta["almacenes_qs"],
        almacen_default=contexto_venta["almacen_default"],
        nota_guardada=nota_guardada,
    )


@permiso_requerido("ventas.add_notaventa")
@transaction.atomic
def salida_venta_create(request):
    DetalleFormSet = _get_detalle_formset_factory(can_delete=True)
    contexto_venta = get_contexto_salida_venta()

    almacen_default = contexto_venta["almacen_default"]

    if not almacen_default:
        messages.error(
            request,
            "No hay almacenes activos. Crea al menos uno para operar inventario.",
        )
        return redirect("almacenes_create")

    if request.method == "POST":
        form = SalidaVentaForm(request.POST)
        formset = DetalleFormSet(
            request.POST,
            queryset=SalidaInventarioDetalle.objects.none(),
        )

        if not form.is_valid() or not formset.is_valid():
            messages.error(request, "Revisa los datos. Hay campos inválidos.")

            return _render_salida_venta_desde_contexto(
                request=request,
                form=form,
                formset=formset,
                contexto_venta=contexto_venta,
            )

        almacenes_permitidos = {
            str(almacen.id): almacen
            for almacen in contexto_venta["almacenes_qs"]
        }

        parser = VentaPostParser(
            post_data=request.POST,
            formset=formset,
            almacenes_permitidos=almacenes_permitidos,
        )

        resultado_parseo = parser.parse()
        errores_parseo = resultado_parseo["errores"]

        if errores_parseo:
            for error in errores_parseo:
                messages.error(request, error)

            return _render_salida_venta_desde_contexto(
                request=request,
                form=form,
                formset=formset,
                contexto_venta=contexto_venta,
            )

        subtotal_venta = total_detalles_venta(resultado_parseo["detalles_validos"])
        total_venta_validacion = calcular_total_con_comision(
            subtotal_venta,
            forma_pago=form.cleaned_data.get("forma_pago_venta"),
        )
        venta_data = VentaOperacionData.from_form(
            form,
            request_context=VentaRequestContext.from_request(request),
            total_venta_override=total_venta_validacion,
        )
        venta_service = VentaService(
            data=venta_data,
            detalles_validos=resultado_parseo["detalles_validos"],
            detalles_meta=resultado_parseo["detalles_meta"],
            lineas_stock=resultado_parseo["lineas_stock"],
            almacenes_permitidos=almacenes_permitidos,
        )

        errores_stock = venta_service.validar_stock()

        if errores_stock:
            for error in errores_stock:
                messages.error(request, error)

            return _render_salida_venta_desde_contexto(
                request=request,
                form=form,
                formset=formset,
                contexto_venta=contexto_venta,
            )

        salida = venta_service.guardar()

        messages.success(
            request,
            "Venta guardada correctamente. Ya puedes imprimir la nota generada.",
        )

        contexto_actualizado = get_contexto_salida_venta()

        nota_guardada = get_nota_guardada_para_impresion(salida.pk)

        return _render_salida_venta_desde_contexto(
            request=request,
            form=_get_form_venta_inicial(),
            formset=DetalleFormSet(
                queryset=SalidaInventarioDetalle.objects.none()
            ),
            contexto_venta=contexto_actualizado,
            nota_guardada=nota_guardada,
        )

    form = _get_form_venta_inicial()
    formset = DetalleFormSet(queryset=SalidaInventarioDetalle.objects.none())

    return _render_salida_venta_desde_contexto(
        request=request,
        form=form,
        formset=formset,
        contexto_venta=contexto_venta,
    )
