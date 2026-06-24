from django.contrib import messages
from django.db import IntegrityError
from django.db.models import F, Sum, Count, ExpressionWrapper, DecimalField
from django.db.models.functions import Round
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import permiso_requerido
from catalogos.models import Almacen, Proveedor

from ..forms import EntradaManualForm
from ..models import EntradaInventario
from ..services.entradas_manual import EntradaManualInventarioService
from ..services.folios import next_folio_movimiento
from ..services.reversas import ReversaInventarioService
from ..utils import (
    build_productos_conversiones_json,
    productos_con_conversiones_qs,
)


def _render_entrada_manual(request, form, proveedores, almacenes, productos, detalle_json_initial):
    return render(request, "inventarios/entrada_manual_form.html", {
        "form": form,
        "proveedores": proveedores,
        "almacenes": almacenes,
        "productos": productos,
        "productos_conversiones_json": build_productos_conversiones_json(productos, include_peso_variable=True),
        "detalle_json_initial": detalle_json_initial,
    })


@permiso_requerido("inventarios.add_entradainventario")
def entrada_manual_create(request):
    proveedores = Proveedor.objects.filter(activo=True).order_by("nombre")
    almacenes = Almacen.objects.filter(es_activo=True).order_by("tipo", "nombre")
    productos = productos_con_conversiones_qs()

    if request.method == "GET":
        initial = {
            "folio": next_folio_movimiento(tipo="MAN", width=6),
            "fecha": timezone.localdate(),
        }
        proveedor_id = (request.GET.get("proveedor_id") or "").strip()
        if proveedor_id.isdigit():
            initial["proveedor"] = int(proveedor_id)

        form = EntradaManualForm(initial=initial)
        return _render_entrada_manual(
            request=request,
            form=form,
            proveedores=proveedores,
            almacenes=almacenes,
            productos=productos,
            detalle_json_initial="[]",
        )

    form = EntradaManualForm(request.POST)
    detalle_json = request.POST.get("detalle_json", "[]")

    if not form.is_valid():
        messages.error(request, "Corrige los errores del formulario.")
        return _render_entrada_manual(request, form, proveedores, almacenes, productos, detalle_json)

    try:
        EntradaManualInventarioService(usuario=request.user).registrar_desde_form(
            form=form,
            detalle_json=detalle_json,
        )
    except (ValueError, IntegrityError) as exc:
        messages.error(request, str(exc))
        return _render_entrada_manual(request, form, proveedores, almacenes, productos, detalle_json)

    messages.success(request, "Entrada manual registrada correctamente.")
    return redirect("entradas_list")


@permiso_requerido("inventarios.view_entradainventario")
def entradas_list(request):
    almacenes_qs = Almacen.objects.filter(es_activo=True).order_by("tipo", "nombre")
    almacen_id = (request.GET.get("almacen") or "").strip()

    entradas = (
        EntradaInventario.objects
        .select_related("almacen", "almacen_origen", "almacen_destino", "registrado_por")
        .all()
        .prefetch_related("detalles")
        .prefetch_related("detalles__almacen")
        .annotate(
            num_almacenes=Count("detalles__almacen_id", distinct=True),
            total_productos=Sum("detalles__cantidad"),
            total_importe=Round(
                Sum(F("detalles__cantidad") * F("detalles__costo_unitario")),
                2,
            ),
        )
    )

    if almacen_id.isdigit():
        entradas = entradas.filter(detalles__almacen_id=int(almacen_id)).distinct()

    tipo = request.GET.get("tipo")
    tipos_validos = dict(EntradaInventario.TIPO_CHOICES)

    if tipo in tipos_validos:
        entradas = entradas.filter(tipo=tipo)

    entradas = list(entradas)
    for entrada in entradas:
        entrada.reversada = ReversaInventarioService.entrada_manual_esta_reversada(entrada.id)
        entrada.es_reversa = ReversaInventarioService.entrada_es_reversa(entrada)

    context = {
        "entradas": entradas,
        "tipo_actual": tipo,
        "almacenes": almacenes_qs,
        "almacen_id": almacen_id,
        "TIPO_CHOICES": EntradaInventario.TIPO_CHOICES,
    }
    return render(request, "inventarios/entradas_list.html", context)


@permiso_requerido("inventarios.view_entradainventario")
def entrada_detalle(request, pk):
    entrada = get_object_or_404(
        EntradaInventario.objects
        .select_related("almacen", "almacen_origen", "almacen_destino", "registrado_por")
        .prefetch_related("detalles__producto", "detalles__almacen"),
        pk=pk,
    )

    detalles = (
        entrada.detalles.all()
        .select_related("producto", "almacen")
        .annotate(
            importe=ExpressionWrapper(
                F("cantidad") * F("costo_unitario"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        )
    )

    totales = detalles.aggregate(
        total_productos=Sum("cantidad"),
        total_importe=Sum("importe"),
    )

    almacenes_detalle = (
        Almacen.objects
        .filter(entradas_detalle__entrada=entrada)
        .distinct()
        .order_by("tipo", "nombre")
    )

    context = {
        "entrada": entrada,
        "detalles": detalles,
        "almacenes_detalle": almacenes_detalle,
        "total_productos": totales["total_productos"] or 0,
        "total_importe": totales["total_importe"] or 0,
        "entrada_reversada": ReversaInventarioService.entrada_manual_esta_reversada(entrada.id),
        "entrada_es_reversa": ReversaInventarioService.entrada_es_reversa(entrada),
    }
    return render(request, "inventarios/entrada_detalle.html", context)


@permiso_requerido("inventarios.change_inventariostock")
@require_POST
def deshacer_entrada_manual(request, pk):
    try:
        resultado = ReversaInventarioService(usuario=request.user).reversar_entrada_manual(entrada_id=pk)
    except ValueError as exc:
        messages.warning(request, str(exc))
        return redirect("entrada_detalle", pk=pk)
    except IntegrityError as exc:
        messages.error(request, f"No se pudo reversar la entrada manual: {exc}")
        return redirect("entrada_detalle", pk=pk)

    messages.success(request, resultado.mensaje)
    return redirect("entrada_detalle", pk=pk)
