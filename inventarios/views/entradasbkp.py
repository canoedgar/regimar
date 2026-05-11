from django.db import transaction
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from decimal import Decimal

import json

from django.db.models import F, Sum, Count, ExpressionWrapper, DecimalField
from django.db.models.functions import Round

from catalogos.models import Almacen, Proveedor, Producto, ProductoMetricaConversion

from ..models import EntradaInventario, EntradaInventarioDetalle
from ..forms import EntradaManualForm

from ..services.folios import next_folio_movimiento
from ..services.stock import aplicar_movimiento_stock 


@transaction.atomic
def entrada_manual_create(request):
    proveedores = Proveedor.objects.filter(activo=True).order_by("nombre")
    almacenes = Almacen.objects.all().order_by("tipo", "nombre")

    productos = Producto.objects.prefetch_related("conversiones_metricas").order_by("nombre")

    if request.method == "GET":
        initial = {
            "folio": next_folio_movimiento(tipo="MAN", width=6),
            "fecha": timezone.localdate(),
        }

        form = EntradaManualForm(initial=initial)

        return render(request, "inventarios/entrada_manual_form.html", {
            "form": form,
            "proveedores": proveedores,
            "almacenes": almacenes,
            "productos": productos,
            "detalle_json_initial": "[]",
        })

    form = EntradaManualForm(request.POST)

    detalle_json = request.POST.get("detalle_json", "[]")
    try:
        detalle = json.loads(detalle_json)
    except Exception:
        detalle = []

    if not form.is_valid():
        messages.error(request, "Corrige los errores del formulario.")
        return render(request, "inventarios/entrada_manual_form.html", {
            "form": form,
            "proveedores": proveedores,
            "almacenes": almacenes,
            "productos": productos,
            "detalle_json_initial": detalle_json,
        })

    if not detalle:
        messages.error(request, "Debes agregar al menos un producto.")
        return render(request, "inventarios/entrada_manual_form.html", {
            "form": form,
            "proveedores": proveedores,
            "almacenes": almacenes,
            "productos": productos,
            "detalle_json_initial": detalle_json,
        })

    detalle_norm = []

    for i, d in enumerate(detalle, start=1):
        try:
            producto_id = int(d.get("producto_id"))
            almacen_id = int(d.get("almacen_id"))
        except:
            messages.error(request, f"Línea {i}: datos inválidos.")
            break

        try:
            cantidad_input = Decimal(str(d.get("cantidad", 0)))
        except:
            cantidad_input = Decimal("0")

        try:
            costo_unitario = Decimal(str(d.get("costo_unitario", 0)))
        except:
            costo_unitario = Decimal("0")

        conversion_id = d.get("conversion_id")

        if cantidad_input <= 0:
            messages.error(request, f"Línea {i}: cantidad inválida.")
            break
        
        cantidad = cantidad_input

        if conversion_id:
            try:
                conversion = ProductoMetricaConversion.objects.get(
                    id=conversion_id,
                    producto_id=producto_id
                )
                cantidad = conversion.convertir_a_default(cantidad_input)
            except ProductoMetricaConversion.DoesNotExist:
                messages.error(request, f"Línea {i}: conversión inválida.")
                break

        detalle_norm.append({
            "producto_id": producto_id,
            "almacen_id": almacen_id,
            "cantidad": cantidad, 
            "cantidad_original": cantidad_input,
            "conversion_id": conversion_id,
            "costo_unitario": costo_unitario,
        })

    else:
        entrada = form.save(commit=False)
        entrada.tipo = EntradaInventario.TIPO_ENTRADA_MANUAL
        entrada.save()

        agregados = {}

        for d in detalle_norm:
            EntradaInventarioDetalle.objects.create(
                entrada=entrada,
                producto_id=d["producto_id"],
                almacen_id=d["almacen_id"],
                cantidad=d["cantidad"],
                costo_unitario=d["costo_unitario"],
            )

            key = (d["producto_id"], d["almacen_id"])
            agregados[key] = agregados.get(key, Decimal("0")) + d["cantidad"]
        
        for (producto_id, almacen_id), cantidad in agregados.items():
            aplicar_movimiento_stock(
                producto_id=producto_id,
                almacen_id=almacen_id,
                delta=cantidad,
            )

        messages.success(request, "Entrada manual registrada correctamente.")
        return redirect("entradas_list")

    return render(request, "inventarios/entrada_manual_form.html", {
        "form": form,
        "proveedores": proveedores,
        "almacenes": almacenes,
        "productos": productos,
        "detalle_json_initial": detalle_json,
    })

def entradas_list(request):
    almacenes_qs = Almacen.objects.filter(es_activo=True).order_by("tipo", "nombre")
    almacen_id = (request.GET.get("almacen") or "").strip()

    entradas = (
        EntradaInventario.objects
        .select_related("almacen")
        .all()
        .prefetch_related("detalles")
        .prefetch_related("detalles__almacen")
        .annotate(
            num_almacenes=Count("detalles__almacen_id", distinct=True),
            total_productos=Sum("detalles__cantidad"),
            total_importe=
            Round(
                Sum(F("detalles__cantidad") * F("detalles__costo_unitario")),
                2
            ),
        )
    )

    if almacen_id.isdigit():
        entradas = entradas.filter(detalles__almacen_id=int(almacen_id)).distinct()


    tipo = request.GET.get("tipo")
    tipos_validos = dict(EntradaInventario.TIPO_CHOICES)

    if tipo in tipos_validos:
        entradas = entradas.filter(tipo=tipo)

    context = {
        "entradas": entradas,
        "tipo_actual": tipo,
        "almacenes": almacenes_qs,
        "almacen_id": almacen_id,
        "TIPO_CHOICES": EntradaInventario.TIPO_CHOICES,
    }
    return render(request, "inventarios/entradas_list.html", context)

def entrada_detalle(request, pk):
    entrada = get_object_or_404(
        EntradaInventario.objects
        .select_related("almacen")
        .prefetch_related("detalles__producto", "detalles__almacen"),
        pk=pk
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

    context = {
        "entrada": entrada,
        "detalles": detalles,
        "total_productos": totales["total_productos"] or 0,
        "total_importe": totales["total_importe"] or 0,
    }
    return render(request, "inventarios/entrada_detalle.html", context)

