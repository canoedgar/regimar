from django.db import transaction, IntegrityError
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from accounts.decorators import grupos_requeridos, permiso_requerido
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from decimal import Decimal, InvalidOperation

import json

from django.db.models import F, Sum, Count, ExpressionWrapper, DecimalField
from django.db.models.functions import Round

from catalogos.models import Almacen, Proveedor, Producto, ProductoMetricaConversion

from ..models import (
    EntradaInventario, EntradaInventarioDetalle,
    SalidaInventario, SalidaInventarioDetalle,
    InventarioStock,
)
from ..forms import EntradaManualForm

from ..services.folios import next_folio_movimiento
from ..services.stock import (
    aplicar_movimiento_stock,
    aplicar_entrada_con_costo,
    recalcular_costo_promedio_producto,
)


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



def _folio_reversa_entrada_manual(folio_original, movimiento_id):
    """
    Genera un folio de reversa único compatible con max_length=20.
    """
    base = f"REV-{folio_original}"
    if len(base) > 20:
        base = f"REV-{movimiento_id}"

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


def _marcador_reversa_entrada_manual(entrada_id):
    return f"REVERSA_DE=entrada_manual:{entrada_id}"


def _entrada_manual_esta_reversada(entrada_id):
    return SalidaInventario.objects.filter(
        observaciones__icontains=_marcador_reversa_entrada_manual(entrada_id)
    ).exists()


def _entrada_es_reversa(entrada):
    return "REVERSA_DE=" in (entrada.observaciones or "")

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

    try:
        with transaction.atomic():
            entrada = form.save(commit=False)
            entrada.tipo = EntradaInventario.TIPO_ENTRADA_MANUAL
            entrada.registrado_por = request.user if request.user.is_authenticated else None
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
    except IntegrityError as exc:
        messages.error(request, f"No se pudo registrar la entrada manual: {exc}")
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

    entradas = list(entradas)
    for entrada in entradas:
        entrada.reversada = _entrada_manual_esta_reversada(entrada.id)
        entrada.es_reversa = _entrada_es_reversa(entrada)

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
        "entrada_reversada": _entrada_manual_esta_reversada(entrada.id),
        "entrada_es_reversa": _entrada_es_reversa(entrada),
    }
    return render(request, "inventarios/entrada_detalle.html", context)

@permiso_requerido("inventarios.change_inventariostock")
@require_POST
def deshacer_entrada_manual(request, pk):
    if _entrada_manual_esta_reversada(pk):
        messages.warning(request, "Esta entrada manual ya tiene una reversa registrada.")
        return redirect("entrada_detalle", pk=pk)

    try:
        with transaction.atomic():
            entrada = get_object_or_404(
                EntradaInventario.objects.select_for_update().prefetch_related("detalles__producto", "detalles__almacen"),
                pk=pk,
                tipo=EntradaInventario.TIPO_ENTRADA_MANUAL,
            )

            if _entrada_es_reversa(entrada):
                raise IntegrityError("No se puede reversar una entrada que ya corresponde a una reversa automática.")

            detalles = list(entrada.detalles.select_related("producto", "almacen"))
            if not detalles:
                raise IntegrityError("La entrada manual no tiene detalle para reversar.")

            acumulado = {}
            for detalle in detalles:
                almacen = detalle.almacen or entrada.almacen
                if not almacen:
                    raise IntegrityError(f"El producto {detalle.producto} no tiene almacén definido.")

                cantidad = _decimal_safe(detalle.cantidad)
                if cantidad <= 0:
                    raise IntegrityError(f"El producto {detalle.producto} tiene cantidad inválida para reversar.")

                key = (detalle.producto_id, almacen.id)
                acumulado[key] = acumulado.get(key, Decimal("0")) + cantidad

            for (producto_id, almacen_id), cantidad_total in acumulado.items():
                stock_row = InventarioStock.objects.select_for_update().filter(
                    producto_id=producto_id,
                    almacen_id=almacen_id,
                ).first()
                stock_actual = _decimal_safe(stock_row.cantidad if stock_row else 0)
                if stock_actual < cantidad_total:
                    raise IntegrityError(
                        f"No se puede reversar porque dejaría inventario negativo. "
                        f"Producto ID {producto_id}, almacén ID {almacen_id}. "
                        f"Disponible: {stock_actual}, requerido: {cantidad_total}."
                    )

            folio = _folio_reversa_entrada_manual(entrada.folio, entrada.id)
            marcador = _marcador_reversa_entrada_manual(entrada.id)
            salida = SalidaInventario.objects.create(
                folio=folio,
                fecha=timezone.localdate(),
                proveedor="",
                tipo=SalidaInventario.TIPO_AJUSTE_NEGATIVO,
                motivo="Reversa de entrada manual",
                observaciones=f"Reversa automática de la entrada manual {entrada.folio}.\n{marcador}",
                almacen=entrada.almacen,
                registrado_por=request.user if request.user.is_authenticated else None,
            )

            productos_recalculados = set()
            for detalle in detalles:
                almacen = detalle.almacen or entrada.almacen
                cantidad = _decimal_safe(detalle.cantidad)
                costo_unitario = _decimal_safe(detalle.costo_unitario)

                SalidaInventarioDetalle.objects.create(
                    salida=salida,
                    producto=detalle.producto,
                    almacen=almacen,
                    presentacion_nombre=detalle.presentacion_nombre,
                    presentacion_conversion_id=detalle.presentacion_conversion_id,
                    cantidad_presentacion=detalle.cantidad_presentacion,
                    presentacion_factor_conversion=detalle.presentacion_factor_conversion,
                    presentacion_metrica_default=detalle.presentacion_metrica_default,
                    presentacion_equivalencia_texto=detalle.presentacion_equivalencia_texto,
                    cantidad=cantidad,
                    precio_unitario=costo_unitario,
                    costo_unitario_aplicado=costo_unitario,
                )

                aplicar_movimiento_stock(
                    producto_id=detalle.producto_id,
                    almacen_id=almacen.id,
                    delta=-cantidad,
                )
                productos_recalculados.add(detalle.producto_id)

            for producto_id in productos_recalculados:
                recalcular_costo_promedio_producto(producto_id)

    except IntegrityError as exc:
        messages.error(request, f"No se pudo reversar la entrada manual: {exc}")
        return redirect("entrada_detalle", pk=pk)

    messages.success(request, f"Se reversó la entrada manual {entrada.folio} con la salida {folio}.")
    return redirect("entrada_detalle", pk=pk)

