from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction, IntegrityError
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import permiso_requerido
from catalogos.models import Almacen

from ..models import (
    EntradaInventario, EntradaInventarioDetalle,
    SalidaInventario, SalidaInventarioDetalle,
    InventarioStock,
)
from ..utils import get_almacen_default
from ..services.stock import (
    aplicar_movimiento_stock,
    aplicar_entrada_con_costo,
    recalcular_costo_promedio_producto,
)
from ..services.folios import next_folio_movimiento
from ..forms import AjusteInventarioForm


def _decimal(value, default="0"):
    try:
        if value in (None, ""):
            return Decimal(default)
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _render_ajuste(request, form, almacenes_qs, almacen, status=200):
    recientes = _ajustes_recientes(limit=10)
    return render(request, "inventarios/ajuste_inventario.html", {
        "form": form,
        "almacenes": almacenes_qs,
        "almacen": almacen,
        "ajustes_recientes": recientes,
    }, status=status)


def _stock_actual(producto_id, almacen_id):
    stock_row = InventarioStock.objects.filter(
        producto_id=producto_id,
        almacen_id=almacen_id,
    ).first()
    return _decimal(stock_row.cantidad if stock_row else 0)


def _folio_reversa(prefix, folio_original, movimiento_id):
    """
    Genera un folio único compatible con max_length=20.
    """
    base = f"{prefix}-{folio_original}"
    if len(base) > 20:
        base = f"{prefix}-{movimiento_id}"

    folio = base[:20]
    contador = 1
    while (
        EntradaInventario.objects.filter(folio=folio).exists()
        or SalidaInventario.objects.filter(folio=folio).exists()
    ):
        suffix = f"-{contador}"
        folio = f"{base[:20-len(suffix)]}{suffix}"
        contador += 1
    return folio


def _ajuste_esta_reversado(tipo, movimiento_id):
    marcador = f"REVERSA_DE={tipo}:{movimiento_id}"
    return (
        EntradaInventario.objects.filter(observaciones__icontains=marcador).exists()
        or SalidaInventario.objects.filter(observaciones__icontains=marcador).exists()
    )


def _ajustes_recientes(limit=10):
    entradas = [
        {
            "tipo": "entrada",
            "id": e.id,
            "folio": e.folio,
            "fecha": e.fecha,
            "creado_en": e.creado_en,
            "tipo_display": e.get_tipo_display(),
            "almacen": e.almacen,
            "producto": d.producto if d else None,
            "cantidad": d.cantidad if d else Decimal("0"),
            "reversado": _ajuste_esta_reversado("entrada", e.id),
        }
        for e in EntradaInventario.objects.filter(tipo=EntradaInventario.TIPO_AJUSTE_POSITIVO)
        .exclude(observaciones__icontains="REVERSA_DE=")
        .select_related("almacen")
        .prefetch_related("detalles__producto")
        .order_by("-creado_en")[:limit]
        for d in [e.detalles.first()]
    ]

    salidas = [
        {
            "tipo": "salida",
            "id": s.id,
            "folio": s.folio,
            "fecha": s.fecha,
            "creado_en": s.creado_en,
            "tipo_display": s.get_tipo_display(),
            "almacen": s.almacen,
            "producto": d.producto if d else None,
            "cantidad": d.cantidad if d else Decimal("0"),
            "reversado": _ajuste_esta_reversado("salida", s.id),
        }
        for s in SalidaInventario.objects.filter(tipo=SalidaInventario.TIPO_AJUSTE_NEGATIVO)
        .exclude(observaciones__icontains="REVERSA_DE=")
        .select_related("almacen")
        .prefetch_related("detalles__producto")
        .order_by("-creado_en")[:limit]
        for d in [s.detalles.first()]
    ]

    movimientos = entradas + salidas
    movimientos.sort(key=lambda x: x["creado_en"], reverse=True)
    return movimientos[:limit]


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

    folio = form.cleaned_data["folio"]
    fecha = timezone.localdate()
    producto = form.cleaned_data["producto"]
    cantidad = form.cleaned_data["cantidad"]
    precio_unitario = form.cleaned_data["precio_unitario"]
    tipo_ajuste = form.cleaned_data["tipo_ajuste"]
    motivo = (form.cleaned_data.get("motivo") or "").strip()
    observaciones = (form.cleaned_data.get("observaciones") or "").strip()
    obs = "\n".join([x for x in [motivo, observaciones] if x]).strip()

    if cantidad is None or cantidad <= 0:
        messages.error(request, "La cantidad debe ser mayor a 0.")
        return _render_ajuste(request, form, almacenes_qs, almacen, status=400)

    if EntradaInventario.objects.filter(folio=folio).exists() or SalidaInventario.objects.filter(folio=folio).exists():
        messages.error(request, f"El folio {folio} ya existe. Intenta nuevamente.")
        return _render_ajuste(request, form, almacenes_qs, almacen, status=400)

    try:
        with transaction.atomic():
            # AJUSTE POSITIVO = entrada
            if tipo_ajuste == AjusteInventarioForm.TIPO_AJUSTE_POSITIVO:
                entrada = EntradaInventario.objects.create(
                    folio=folio,
                    fecha=fecha,
                    proveedor=None,
                    tipo=EntradaInventario.TIPO_AJUSTE_POSITIVO,
                    motivo=motivo,
                    observaciones=obs,
                    almacen=almacen,
                )

                EntradaInventarioDetalle.objects.create(
                    entrada=entrada,
                    producto=producto,
                    almacen=almacen,
                    cantidad=cantidad,
                    costo_unitario=precio_unitario,
                )

                aplicar_entrada_con_costo(
                    producto_id=producto.pk,
                    almacen_id=almacen.id,
                    cantidad=cantidad,
                    costo_unitario=precio_unitario,
                    usuario=request.user,
                    motivo_bitacora="Ajuste positivo de inventario",
                )

                mensaje = f"Ajuste positivo aplicado en {almacen}. Folio: {folio}"

            else:
                stock_row = InventarioStock.objects.select_for_update().filter(
                    producto_id=producto.pk,
                    almacen_id=almacen.id,
                ).first()
                stock_actual = _decimal(stock_row.cantidad if stock_row else 0)

                if stock_actual < cantidad:
                    messages.error(
                        request,
                        f"Stock insuficiente para '{producto}'. Disponible en {almacen}: {stock_actual} | Requerido: {cantidad}"
                    )
                    return _render_ajuste(request, form, almacenes_qs, almacen, status=400)

                salida = SalidaInventario.objects.create(
                    folio=folio,
                    fecha=fecha,
                    proveedor="",
                    tipo=SalidaInventario.TIPO_AJUSTE_NEGATIVO,
                    motivo=motivo,
                    observaciones=obs,
                    almacen=almacen,
                )

                SalidaInventarioDetalle.objects.create(
                    salida=salida,
                    producto=producto,
                    almacen=almacen,
                    cantidad=cantidad,
                    precio_unitario=precio_unitario,
                    costo_unitario_aplicado=getattr(producto, "costo_promedio", 0) or 0,
                )

                aplicar_movimiento_stock(
                    producto_id=producto.pk,
                    almacen_id=almacen.id,
                    delta=-cantidad,
                )
                recalcular_costo_promedio_producto(producto.pk)

                try:
                    producto.refresh_from_db()
                    from catalogos.services.precios import registrar_bitacora_precio_producto
                    registrar_bitacora_precio_producto(
                        producto,
                        usuario=request.user,
                        motivo="Ajuste negativo de inventario",
                    )
                except Exception:
                    pass

                mensaje = f"Ajuste negativo aplicado en {almacen}. Folio: {folio}"

    except IntegrityError as exc:
        messages.error(request, f"No se pudo aplicar el ajuste: {exc}")
        return _render_ajuste(request, form, almacenes_qs, almacen, status=400)

    messages.success(request, mensaje)
    return redirect("ajuste_inventario")


@permiso_requerido("inventarios.view_inventariostock")
def ajuste_stock_preview(request):
    producto_id = (request.GET.get("producto_id") or "").strip()
    almacen_id = (request.GET.get("almacen_id") or "").strip()
    tipo_ajuste = (request.GET.get("tipo_ajuste") or "").strip()
    cantidad = _decimal(request.GET.get("cantidad"), default="0")

    if not producto_id.isdigit() or not almacen_id.isdigit():
        return JsonResponse({"ok": False, "message": "Selecciona almacén y producto."})

    stock_actual = _stock_actual(int(producto_id), int(almacen_id))
    delta = cantidad if tipo_ajuste == AjusteInventarioForm.TIPO_AJUSTE_POSITIVO else -cantidad
    stock_resultante = stock_actual + delta
    permite = cantidad > 0 and stock_resultante >= 0

    stock_row = InventarioStock.objects.filter(producto_id=producto_id, almacen_id=almacen_id).first()
    costo_promedio = _decimal(getattr(stock_row, "costo_promedio", 0) if stock_row else 0)

    message = ""
    if cantidad <= 0:
        message = "Captura una cantidad mayor a 0 para calcular el resultado."
    elif not permite:
        message = "El ajuste dejaría inventario negativo. Reduce la cantidad o selecciona otro almacén."
    else:
        message = "El ajuste puede aplicarse sin dejar inventario negativo."

    return JsonResponse({
        "ok": True,
        "stock_actual": str(stock_actual),
        "stock_resultante": str(stock_resultante),
        "cantidad": str(cantidad),
        "costo_promedio": str(costo_promedio),
        "permite": permite,
        "message": message,
    })


@permiso_requerido("inventarios.change_inventariostock")
@require_POST
def deshacer_ajuste(request, tipo, pk):
    if tipo not in {"entrada", "salida"}:
        messages.error(request, "Tipo de ajuste inválido.")
        return redirect("ajuste_inventario")

    if _ajuste_esta_reversado(tipo, pk):
        messages.warning(request, "Este ajuste ya tiene una reversa registrada.")
        return redirect("ajuste_inventario")

    try:
        with transaction.atomic():
            if tipo == "entrada":
                entrada_original = get_object_or_404(
                    EntradaInventario.objects.select_for_update(),
                    pk=pk,
                    tipo=EntradaInventario.TIPO_AJUSTE_POSITIVO,
                )
                detalle = entrada_original.detalles.select_related("producto", "almacen").first()
                if not detalle:
                    raise IntegrityError("El ajuste positivo no tiene detalle para reversar.")

                almacen = detalle.almacen or entrada_original.almacen
                if not almacen:
                    raise IntegrityError("El ajuste positivo no tiene almacén definido.")

                stock_row = InventarioStock.objects.select_for_update().filter(
                    producto_id=detalle.producto_id,
                    almacen_id=almacen.id,
                ).first()
                stock_actual = _decimal(stock_row.cantidad if stock_row else 0)
                cantidad = _decimal(detalle.cantidad)
                if stock_actual < cantidad:
                    raise IntegrityError(
                        f"No se puede deshacer porque dejaría inventario negativo. Disponible: {stock_actual}, requerido: {cantidad}."
                    )

                folio = _folio_reversa("REV", entrada_original.folio, entrada_original.id)
                marcador = f"REVERSA_DE=entrada:{entrada_original.id}"
                salida = SalidaInventario.objects.create(
                    folio=folio,
                    fecha=timezone.localdate(),
                    proveedor="",
                    tipo=SalidaInventario.TIPO_AJUSTE_NEGATIVO,
                    motivo="Reversa de ajuste positivo",
                    observaciones=f"Reversa automática del ajuste {entrada_original.folio}.\n{marcador}",
                    almacen=almacen,
                )
                SalidaInventarioDetalle.objects.create(
                    salida=salida,
                    producto=detalle.producto,
                    almacen=almacen,
                    cantidad=cantidad,
                    precio_unitario=detalle.costo_unitario,
                    costo_unitario_aplicado=getattr(detalle.producto, "costo_promedio", 0) or 0,
                )
                aplicar_movimiento_stock(producto_id=detalle.producto_id, almacen_id=almacen.id, delta=-cantidad)
                recalcular_costo_promedio_producto(detalle.producto_id)
                mensaje = f"Se reversó el ajuste positivo {entrada_original.folio} con la salida {folio}."

            else:
                salida_original = get_object_or_404(
                    SalidaInventario.objects.select_for_update(),
                    pk=pk,
                    tipo=SalidaInventario.TIPO_AJUSTE_NEGATIVO,
                )
                detalle = salida_original.detalles.select_related("producto", "almacen").first()
                if not detalle:
                    raise IntegrityError("El ajuste negativo no tiene detalle para reversar.")

                almacen = detalle.almacen or salida_original.almacen
                if not almacen:
                    raise IntegrityError("El ajuste negativo no tiene almacén definido.")

                cantidad = _decimal(detalle.cantidad)
                costo_reversa = _decimal(detalle.costo_unitario_aplicado or detalle.precio_unitario)
                folio = _folio_reversa("REV", salida_original.folio, salida_original.id)
                marcador = f"REVERSA_DE=salida:{salida_original.id}"
                entrada = EntradaInventario.objects.create(
                    folio=folio,
                    fecha=timezone.localdate(),
                    proveedor=None,
                    tipo=EntradaInventario.TIPO_AJUSTE_POSITIVO,
                    motivo="Reversa de ajuste negativo",
                    observaciones=f"Reversa automática del ajuste {salida_original.folio}.\n{marcador}",
                    almacen=almacen,
                )
                EntradaInventarioDetalle.objects.create(
                    entrada=entrada,
                    producto=detalle.producto,
                    almacen=almacen,
                    cantidad=cantidad,
                    costo_unitario=costo_reversa,
                )
                aplicar_entrada_con_costo(
                    producto_id=detalle.producto_id,
                    almacen_id=almacen.id,
                    cantidad=cantidad,
                    costo_unitario=costo_reversa,
                    usuario=request.user,
                    motivo_bitacora="Reversa de ajuste negativo de inventario",
                )
                mensaje = f"Se reversó el ajuste negativo {salida_original.folio} con la entrada {folio}."

    except IntegrityError as exc:
        messages.error(request, f"No se pudo deshacer el ajuste: {exc}")
        return redirect("ajuste_inventario")

    messages.success(request, mensaje)
    return redirect("ajuste_inventario")
