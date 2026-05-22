from django.db import transaction, IntegrityError
from django.contrib import messages
from django.shortcuts import render, redirect
from django.utils import timezone

from catalogos.models import Almacen

from ..models import (
    EntradaInventario, EntradaInventarioDetalle,
    SalidaInventario, SalidaInventarioDetalle,
    InventarioStock
)

from ..utils import get_almacen_default
from ..services.stock import aplicar_movimiento_stock, aplicar_entrada_con_costo, recalcular_costo_promedio_producto
from ..services.folios import next_folio_movimiento
from ..forms import AjusteInventarioForm


@transaction.atomic
def ajuste_inventario(request):
    almacenes_qs = Almacen.objects.filter(es_activo=True).order_by("tipo", "nombre")

    # default y fallback
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
        return render(request, "inventarios/ajuste_inventario.html", {
            "form": form,
            "almacenes": almacenes_qs,
            "almacen": almacen,
        })

    # POST
    almacen_id = (request.POST.get("almacen_id") or "").strip()
    if almacen_id.isdigit():
        almacen = almacenes_qs.filter(pk=int(almacen_id)).first() or almacen

    form = AjusteInventarioForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Revisa los datos del ajuste.")
        return render(request, "inventarios/ajuste_inventario.html", {
            "form": form,
            "almacenes": almacenes_qs,
            "almacen": almacen,
        })

    # Forzamos fecha en servidor
    folio = form.cleaned_data["folio"]
    fecha = timezone.localdate()
    producto = form.cleaned_data["producto"]
    cantidad = form.cleaned_data["cantidad"]
    precio_unitario = form.cleaned_data["precio_unitario"]
    tipo_ajuste = form.cleaned_data["tipo_ajuste"]
    motivo = (form.cleaned_data.get("motivo") or "").strip()
    observaciones = (form.cleaned_data.get("observaciones") or "").strip()
    obs = "\n".join([x for x in [motivo, observaciones] if x]).strip()

    # Evitar duplicidad
    if EntradaInventario.objects.filter(folio=folio).exists() or SalidaInventario.objects.filter(folio=folio).exists():
        messages.error(request, f"El folio {folio} ya existe. Intenta nuevamente.")
        return render(request, "inventarios/ajuste_inventario.html", {
            "form": form,
            "almacenes": almacenes_qs,
            "almacen": almacen,
        })

    # Validaciones adicionales
    if cantidad is None or cantidad <= 0:
        messages.error(request, "La cantidad debe ser mayor a 0.")
        return render(request, "inventarios/ajuste_inventario.html", {
            "form": form,
            "almacenes": almacenes_qs,
            "almacen": almacen,
        })

    try:
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

            messages.success(request, f"Ajuste positivo aplicado en {almacen}. Folio: {folio}")
            return redirect("inventario_actual")

        # AJUSTE NEGATIVO = salida (validar stock por almacén)
        stock_row = InventarioStock.objects.select_for_update().filter(
            producto_id=producto.pk,
            almacen_id=almacen.id
        ).first()
        stock_actual = (stock_row.cantidad if stock_row and stock_row.cantidad is not None else 0)

        if stock_actual < cantidad:
            messages.error(
                request,
                f"Stock insuficiente para '{producto}'. Disponible en {almacen}: {stock_actual} | Requerido: {cantidad}"
            )
            return render(request, "inventarios/ajuste_inventario.html", {
                "form": form,
                "almacenes": almacenes_qs,
                "almacen": almacen,
            })

        salida = SalidaInventario.objects.create(
            folio=folio,
            fecha=fecha,
            proveedor=None,
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
            delta=-cantidad
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

        messages.success(request, f"Ajuste negativo aplicado en {almacen}. Folio: {folio}")
        return redirect("inventario_actual")

    except IntegrityError:
        messages.error(request, "No se pudo aplicar el ajuste. Intenta nuevamente.")
        return render(request, "inventarios/ajuste_inventario.html", {
            "form": form,
            "almacenes": almacenes_qs,
            "almacen": almacen,
        })
