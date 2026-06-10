from django.db import transaction
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from accounts.decorators import grupos_requeridos, permiso_requerido
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
from ..services.stock import aplicar_movimiento_stock, aplicar_entrada_con_costo


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
            "maneja_peso_variable": bool(getattr(producto, "maneja_peso_variable", False)),
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


@permiso_requerido("inventarios.add_entradainventario")
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

        producto = Producto.objects.filter(id=producto_id).first()
        if not producto:
            messages.error(request, f"Línea {i}: producto inválido.")
            return _render_entrada_manual(request, form, proveedores, almacenes, productos, detalle_json)

        costo_unitario = _decimal_safe(d.get("costo_unitario"))
        if costo_unitario < 0:
            messages.error(request, f"Línea {i}: el costo unitario no puede ser negativo.")
            return _render_entrada_manual(request, form, proveedores, almacenes, productos, detalle_json)

        metrica_base = getattr(producto, "metrica", None) or "kg"
        maneja_peso_variable = bool(getattr(producto, "maneja_peso_variable", False))
        conversion = None
        conversion_id = None

        if maneja_peso_variable:
            cantidad_cajas = _decimal_safe(d.get("cantidad_cajas") or d.get("cantidad_original"))
            kilos_reales = _decimal_safe(d.get("kilos_reales") or d.get("cantidad_convertida") or d.get("cantidad"))

            if cantidad_cajas <= 0:
                messages.error(request, f"Línea {i}: captura la cantidad de cajas para el producto de peso variable.")
                return _render_entrada_manual(request, form, proveedores, almacenes, productos, detalle_json)

            if kilos_reales <= 0:
                messages.error(request, f"Línea {i}: captura los kilos reales para el producto de peso variable.")
                return _render_entrada_manual(request, form, proveedores, almacenes, productos, detalle_json)

            cantidad_default = kilos_reales
            cantidad_input = cantidad_cajas
            presentacion_nombre = "Caja peso variable"
            factor_conversion = (kilos_reales / cantidad_cajas) if cantidad_cajas > 0 else Decimal("0")
            equivalencia_texto = f"{_decimal_texto(cantidad_cajas)} cajas = {_decimal_texto(kilos_reales)} {metrica_base} reales"
            presentacion_conversion_id = "peso_variable"
            cantidad_presentacion = cantidad_cajas
            cantidad_cajas_guardar = cantidad_cajas
            kilos_reales_guardar = kilos_reales
        else:
            cantidad_input = _decimal_safe(d.get("cantidad"))
            conversion_id_raw = d.get("conversion_id")
            conversion_id = int(conversion_id_raw) if str(conversion_id_raw or "").isdigit() else None

            if cantidad_input <= 0:
                messages.error(request, f"Línea {i}: la cantidad debe ser mayor a 0.")
                return _render_entrada_manual(request, form, proveedores, almacenes, productos, detalle_json)

            cantidad_default = cantidad_input
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

            presentacion_nombre = metrica_base
            equivalencia_texto = f"Base ({metrica_base})"
            factor_conversion = Decimal("1")
            presentacion_conversion_id = str(conversion_id or "default")
            cantidad_presentacion = cantidad_input
            cantidad_cajas_guardar = Decimal("0")
            kilos_reales_guardar = Decimal("0")

            if conversion:
                presentacion_nombre = conversion.unidad_origen or conversion.nombre
                equivalencia_texto = conversion.equivalencia_texto
                factor_conversion = conversion.factor_conversion

        costo_total = cantidad_default * costo_unitario

        detalle_norm.append({
            "producto_id": producto_id,
            "almacen_id": almacen_id,
            "cantidad": cantidad_default,
            "cantidad_original": cantidad_input,
            "conversion_id": conversion_id,
            "costo_unitario": costo_unitario,
            "conversion": conversion,
            "presentacion_nombre": presentacion_nombre,
            "presentacion_conversion_id": presentacion_conversion_id,
            "cantidad_presentacion": cantidad_presentacion,
            "presentacion_factor_conversion": factor_conversion,
            "presentacion_metrica_default": metrica_base,
            "presentacion_equivalencia_texto": equivalencia_texto,
            "es_peso_variable": maneja_peso_variable,
            "cantidad_cajas": cantidad_cajas_guardar,
            "kilos_reales": kilos_reales_guardar,
            "costo_total": costo_total,
        })

    entrada = form.save(commit=False)
    entrada.tipo = EntradaInventario.TIPO_ENTRADA_MANUAL
    entrada.save()

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
            es_peso_variable=d["es_peso_variable"],
            cantidad_cajas=d["cantidad_cajas"],
            kilos_reales=d["kilos_reales"],
            costo_total=d["costo_total"],
        )

        aplicar_entrada_con_costo(
            producto_id=d["producto_id"],
            almacen_id=d["almacen_id"],
            cantidad=d["cantidad"],
            costo_unitario=d["costo_unitario"],
            usuario=request.user,
            motivo_bitacora="Entrada manual de inventario",
        )

    messages.success(request, "Entrada manual registrada correctamente.")
    return redirect("entradas_list")


@permiso_requerido("inventarios.view_entradainventario")
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


@permiso_requerido("inventarios.view_entradainventario")
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
    }
    return render(request, "inventarios/entrada_detalle.html", context)
