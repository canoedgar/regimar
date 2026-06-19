from django.contrib import messages
from django.contrib.auth.decorators import login_required
from accounts.decorators import grupos_requeridos, permiso_requerido
from django.db import transaction
from django.forms import modelformset_factory
from django.shortcuts import get_object_or_404, redirect, render

from inventarios.forms import (
    SalidaInventarioDetalleForm,
    SalidaVentaDetallePrecioForm,
    SalidaVentaEdicionForm,
)
from inventarios.models import SalidaInventario, SalidaInventarioDetalle
from inventarios.selectors.notas_venta import (
    get_clientes_activos,
    get_contexto_agregar_productos,
    get_nota_venta_qs_for_404,
)
from inventarios.services.notas_venta import (
    AgregarProductosNotaService,
    AjustarPreciosNotaService,
    EditarDatosNotaService,
)


def _get_nota(pk, *, for_update=False):
    return get_object_or_404(get_nota_venta_qs_for_404(pk, for_update=for_update))


def _validar_editable(salida, request):
    if salida.estado == SalidaInventario.ESTADO_CANCELADA:
        messages.error(request, "No se puede modificar una nota cancelada.")
        return False
    return True


@permiso_requerido("inventarios.view_salidainventario")
def nota_venta_acciones(request, pk):
    salida = _get_nota(pk)
    detalles = salida.detalles.all()
    return render(request, "inventarios/nota_venta_acciones.html", {
        "salida": salida,
        "detalles": detalles,
    })


@permiso_requerido("inventarios.change_salidainventario")
@transaction.atomic
def nota_venta_editar_datos(request, pk):
    salida = _get_nota(pk, for_update=request.method == "POST")
    if not _validar_editable(salida, request):
        return redirect("ventas_list")

    if request.method == "POST":
        form = SalidaVentaEdicionForm(request.POST, instance=salida)
        if form.is_valid():
            service = EditarDatosNotaService(form=form, user=request.user, request=request)
            errores = service.validar()
            if not errores:
                service.execute()
                messages.success(request, f"Datos de la nota {salida.folio} actualizados correctamente.")
                return redirect("nota_venta_acciones", pk=salida.pk)
            for error in errores:
                messages.error(request, error)
        else:
            messages.error(request, "Revisa los datos capturados.")
    else:
        form = SalidaVentaEdicionForm(instance=salida)

    return render(request, "inventarios/nota_venta_editar_datos.html", {
        "salida": salida,
        "form": form,
        "clientes": get_clientes_activos(),
        "detalles": salida.detalles.all(),
    })


@permiso_requerido("inventarios.change_salidainventario")
@transaction.atomic
def nota_venta_ajustar_precios(request, pk):
    salida = _get_nota(pk, for_update=request.method == "POST")
    if not _validar_editable(salida, request):
        return redirect("ventas_list")

    DetallePrecioFormSet = modelformset_factory(
        SalidaInventarioDetalle,
        form=SalidaVentaDetallePrecioForm,
        extra=0,
        can_delete=False,
    )
    detalles_qs = salida.detalles.all().order_by("id")

    if request.method == "POST":
        formset = DetallePrecioFormSet(request.POST, queryset=detalles_qs, prefix="precios")
        if formset.is_valid():
            service = AjustarPreciosNotaService(formset=formset, salida=salida, user=request.user, request=request)
            errores = service.validar()
            if not errores:
                service.execute()
                messages.success(request, f"Precios de la nota {salida.folio} actualizados correctamente.")
                return redirect("nota_venta_acciones", pk=salida.pk)
            for error in errores:
                messages.error(request, error)
        else:
            messages.error(request, "Revisa los precios capturados.")
    else:
        formset = DetallePrecioFormSet(queryset=detalles_qs, prefix="precios")

    contexto = get_contexto_agregar_productos(salida)
    return render(request, "inventarios/nota_venta_ajustar_precios.html", {
        "salida": salida,
        "formset": formset,
        "productos_ui": contexto["productos_ui"],
    })


@permiso_requerido("inventarios.change_salidainventario")
@transaction.atomic
def nota_venta_agregar_productos(request, pk):
    salida = _get_nota(pk, for_update=request.method == "POST")
    if not _validar_editable(salida, request):
        return redirect("ventas_list")

    contexto = get_contexto_agregar_productos(salida)
    almacenes_permitidos = {str(almacen.id): almacen for almacen in contexto["almacenes_qs"]}

    NuevoProductoFormSet = modelformset_factory(
        SalidaInventarioDetalle,
        form=SalidaInventarioDetalleForm,
        extra=0,
        can_delete=True,
    )

    if request.method == "POST":
        formset = NuevoProductoFormSet(
            request.POST,
            queryset=SalidaInventarioDetalle.objects.none(),
            prefix="nuevos",
        )
        service = AgregarProductosNotaService(
            request=request,
            salida=salida,
            formset=formset,
            almacenes_permitidos=almacenes_permitidos,
        )
        errores = service.validar()
        if not errores:
            service.execute()
            messages.success(request, f"Productos agregados correctamente a la nota {salida.folio}.")
            return redirect("nota_venta_acciones", pk=salida.pk)
        for error in errores:
            messages.error(request, error)
    else:
        formset = NuevoProductoFormSet(
            queryset=SalidaInventarioDetalle.objects.none(),
            prefix="nuevos",
        )

    return render(request, "inventarios/nota_venta_agregar_productos.html", {
        "salida": salida,
        "detalles": salida.detalles.all(),
        "nuevos_formset": formset,
        "productos_ui": contexto["productos_ui"],
        "productos_existentes_ids": contexto["productos_existentes_ids"],
        "almacenes": contexto["almacenes_qs"],
    })
