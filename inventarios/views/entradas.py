from django.db import transaction
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from decimal import Decimal, InvalidOperation

import json

from django.db.models import F, Sum, Count, ExpressionWrapper, DecimalField
from django.db.models.functions import Round

from catalogos.models import Almacen, Proveedor, Producto, ProductoMetricaConversion

from ..models import EntradaInventario, EntradaInventarioDetalle
from ..forms import EntradaManualForm

from ..services.folios import next_folio_movimiento
from ..services.stock import aplicar_movimiento_stock


def _decimal_safe(valor, default="0"):
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _decimal_texto(valor):
    valor = _decimal_safe(valor)
    texto = format(valor, "f")
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto or "0"


def _build_productos_conversiones_json(productos):
    data = {}
    for producto in productos:
        conversiones = []
        for conversion in producto.conversiones_metricas.all():
            if not conversion.activo:
                continue
            conversiones.append({
                "id": conversion.id,
                "nombre": conversion.nombre,
                "unidad_origen": conversion.unidad_origen,
                "cantidad_origen": _decimal_texto(conversion.cantidad_origen),
                "factor_conversion": _decimal_texto(conversion.factor_conversion),
                "texto": conversion.equivalencia_texto,
            })

        data[str(producto.id)] = {
            "id": producto.id,
            "nombre": producto.nombre,
            "metrica": producto.metrica or "kg",
            "conversiones": conversiones,
        }
    return data


def _render_entrada_manual(request, form, proveedores, almacenes, productos, detalle_json_initial):
    return render(request, "inventarios/entrada_manual_form.html", {
        "form": form,
        "proveedores": proveedores,
        "almacenes": almacenes,
        "productos": productos,
        "productos_conversiones_json": _build_productos_conversiones_json(productos),
        "detalle_json_initial": detalle_json_initial,
    })


@transaction.atomic
def entrada_manual_create(request):
    proveedores = Proveedor.objects.filter(activo=True).order_by("nombre")
    almacenes = Almacen.objects.filter(es_activo=True).order_by("tipo", "nombre")
    productos = (
        Producto.objects
        .prefetch_related("conversiones_metricas")
        .order_by("nombre")
    )

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

    try:
        detalle = json.loads(detalle_json)
        if not isinstance(detalle, list):
            detalle = []
    except Exception:
        detalle = []

    if not form.is_valid():
        messages.error(request, "Corrige los errores del formulario.")
        return _render_entrada_manual(request, form, proveedores, almacenes, productos, detalle_json)

    if not detalle:
        messages.error(request, "Debes agregar al menos un producto.")
        return _render_entrada_manual(request, form, proveedores, almacenes, productos, detalle_json)

    detalle_norm = []

    for i, d in enumerate(detalle, start=1):
        try:
            producto_id = int(d.get("producto_id"))
            almacen_id = int(d.get("almacen_id"))
        except (TypeError, ValueError):
            messages.error(request, f"Línea {i}: producto o almacén inválido.")
            return _render_entrada_manual(request, form, proveedores, almacenes, productos, detalle_json)

        cantidad_input = _decimal_safe(d.get("cantidad"))
        costo_unitario = _decimal_safe(d.get("costo_unitario"))
        conversion_id = d.get("conversion_id")
        conversion_id = int(conversion_id) if str(conversion_id or "").isdigit() else None

        if cantidad_input <= 0:
            messages.error(request, f"Línea {i}: la cantidad debe ser mayor a 0.")
            return _render_entrada_manual(request, form, proveedores, almacenes, productos, detalle_json)

        if costo_unitario < 0:
            messages.error(request, f"Línea {i}: el costo unitario no puede ser negativo.")
            return _render_entrada_manual(request, form, proveedores, almacenes, productos, detalle_json)

        cantidad_default = cantidad_input
        conversion = None

        if conversion_id:
            try:
                conversion = ProductoMetricaConversion.objects.get(
                    id=conversion_id,
                    producto_id=producto_id,
                    activo=True,
                )
                cantidad_default = conversion.convertir_a_default(cantidad_input)
            except ProductoMetricaConversion.DoesNotExist:
                messages.error(request, f"Línea {i}: la presentación seleccionada ya no es válida para ese producto.")
                return _render_entrada_manual(request, form, proveedores, almacenes, productos, detalle_json)

        producto = Producto.objects.filter(id=producto_id).first()
        metrica_base = (getattr(producto, "metrica", None) or "kg") if producto else "kg"
        presentacion_nombre = metrica_base
        equivalencia_texto = f"Base ({metrica_base})"
        factor_conversion = Decimal("1")

        if conversion:
            presentacion_nombre = conversion.unidad_origen or conversion.nombre
            equivalencia_texto = conversion.equivalencia_texto
            factor_conversion = conversion.factor_conversion

        detalle_norm.append({
            "producto_id": producto_id,
            "almacen_id": almacen_id,
            "cantidad": cantidad_default,
            "cantidad_original": cantidad_input,
            "conversion_id": conversion_id,
            "costo_unitario": costo_unitario,
            "conversion": conversion,
            "presentacion_nombre": presentacion_nombre,
            "presentacion_conversion_id": str(conversion_id or "default"),
            "cantidad_presentacion": cantidad_input,
            "presentacion_factor_conversion": factor_conversion,
            "presentacion_metrica_default": metrica_base,
            "presentacion_equivalencia_texto": equivalencia_texto,
        })

    entrada = form.save(commit=False)
    entrada.tipo = EntradaInventario.TIPO_ENTRADA_MANUAL
    entrada.save()

    agregados = {}

    for d in detalle_norm:
        EntradaInventarioDetalle.objects.create(
            entrada=entrada,
            producto_id=d["producto_id"],
            almacen_id=d["almacen_id"],
            presentacion_nombre=d["presentacion_nombre"],
            presentacion_conversion_id=d["presentacion_conversion_id"],
            cantidad_presentacion=d["cantidad_presentacion"],
            presentacion_factor_conversion=d["presentacion_factor_conversion"],
            presentacion_metrica_default=d["presentacion_metrica_default"],
            presentacion_equivalencia_texto=d["presentacion_equivalencia_texto"],
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
