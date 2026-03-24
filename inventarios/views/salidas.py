from catalogos.models import Almacen, Producto, Cliente
from ..models import SalidaInventario, SalidaInventarioDetalle
from ..forms import SalidaInventarioDetalleForm, SalidaVentaForm, SalidaProyectoForm
from django.db.models import F, Sum, ExpressionWrapper, DecimalField
from django.db.models.functions import Round
from django.db import transaction
from django.contrib import messages
from ..utils import get_almacen_default
from ..services.stock import (agrupar_requeridos_por_producto, validar_stock_suficiente, errores_stock_humano, aplicar_movimientos_salida)
from ..services.folios import next_folio_movimiento
from django.forms import modelformset_factory
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from catalogos.sat_catalogos import REGIMEN_FISCAL_CHOICES

def salidas_list(request):
    almacenes_qs = Almacen.objects.filter(es_activo=True).order_by("tipo", "nombre")
    almacen_id = (request.GET.get("almacen") or "").strip()

    salidas = (
        SalidaInventario.objects
        .select_related("almacen")
        .all()
        .prefetch_related("detalles")
        .annotate(
            total_productos=Sum("detalles__cantidad"),
            total_importe=Round(
                Sum(F("detalles__cantidad") * F("detalles__precio_unitario")),
                2
            ),
        )
    )

    tipo = request.GET.get("tipo")
    tipos_validos = dict(SalidaInventario.TIPO_CHOICES)

    if tipo in tipos_validos:
        salidas = salidas.filter(tipo=tipo)

    if almacen_id.isdigit():
        salidas = salidas.filter(almacen_id=int(almacen_id))

    context = {
        "salidas": salidas,
        "tipo_actual": tipo,
        "almacenes": almacenes_qs,
        "almacen_id": almacen_id,
        "TIPO_CHOICES": SalidaInventario.TIPO_CHOICES,
    }
    return render(request, "inventarios/salidas_list.html", context)


def salida_detalle(request, pk):
    salida = get_object_or_404(
        SalidaInventario.objects
        .select_related("almacen", "proyecto")
        .prefetch_related("detalles__producto"),
        pk=pk
    )

    detalles = (
        salida.detalles.all()
        .select_related("producto")
        .annotate(
            importe=ExpressionWrapper(
                F("cantidad") * F("precio_unitario"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        )
    )

    totales = detalles.aggregate(
        total_productos=Sum("cantidad"),
        total_importe=Sum("importe"),
    )

    return render(request, "inventarios/salida_detalle.html", {
        "salida": salida,
        "detalles": detalles,
        "total_productos": totales["total_productos"] or 0,
        "total_importe": totales["total_importe"] or 0,
    })

@transaction.atomic
def salida_venta_create(request):
    DetalleFormSet = modelformset_factory(
        SalidaInventarioDetalle,
        form=SalidaInventarioDetalleForm,
        extra=0,
        can_delete=True,
    )

    productos = Producto.objects.all().order_by("nombre")
    clientes = Cliente.objects.all().order_by("nombre_fiscal")
    almacenes_qs = Almacen.objects.filter(es_activo=True).order_by("tipo", "nombre")

    almacen = get_almacen_default()
    if not almacen:
        messages.error(request, "No hay almacenes activos. Crea al menos uno para operar inventario.")
        return redirect("almacenes_create")

    # Si viene almacen_id, úsalo (POST)
    if request.method == "POST":
        almacen_id = (request.POST.get("almacen_id") or "").strip()
        if almacen_id.isdigit():
            almacen = almacenes_qs.filter(pk=int(almacen_id)).first() or almacen

    if request.method == "POST":
        form = SalidaVentaForm(request.POST)
        formset = DetalleFormSet(request.POST, queryset=SalidaInventarioDetalle.objects.none())

        if form.is_valid() and formset.is_valid():
            # 1) Preparar detalles válidos
            detalles = formset.save(commit=False)

            detalles_validos = []
            for d in detalles:
                if getattr(d, "DELETE", False):
                    continue
                if not d.producto_id:
                    continue
                if d.cantidad is None or d.cantidad <= 0:
                    messages.error(request, "Hay renglones con cantidad inválida (<= 0).")
                    return render(request, "inventarios/salida_venta_form.html", {
                        "form": form,
                        "formset": formset,
                        "productos": productos,
                        "clientes": clientes,
                        "almacenes": almacenes_qs,
                        "almacen": almacen,
                        "REGIMEN_FISCAL_CHOICES": REGIMEN_FISCAL_CHOICES,
                    })

                detalles_validos.append(d)

            if not detalles_validos:
                messages.error(request, "Agrega al menos un producto a la venta.")
                return render(request, "inventarios/salida_venta_form.html", {
                    "form": form,
                    "formset": formset,
                    "productos": productos,
                    "clientes": clientes,
                    "almacenes": almacenes_qs,
                    "almacen": almacen,
                    "REGIMEN_FISCAL_CHOICES": REGIMEN_FISCAL_CHOICES,
                })

            # 2) Validar stock (sumando productos repetidos)
            requeridos = agrupar_requeridos_por_producto(
                (d.producto_id, d.cantidad) for d in detalles_validos
            )

            productos_por_id = {
                p.id: str(p)
                for p in Producto.objects.filter(id__in=requeridos.keys())
            }

            ok, disponibles, faltantes = validar_stock_suficiente(
                almacen_id=almacen.id,
                requeridos=requeridos,
            )

            if not ok:
                for msg in errores_stock_humano(
                    almacen_nombre=str(almacen),
                    faltantes=faltantes,
                    disponibles=disponibles,
                    productos_por_id=productos_por_id,
                ):
                    messages.error(request, msg)

                return render(request, "inventarios/salida_venta_form.html", {
                    "form": form,
                    "formset": formset,
                    "productos": productos,
                    "clientes": clientes,
                    "almacenes": almacenes_qs,
                    "almacen": almacen,
                    "REGIMEN_FISCAL_CHOICES": REGIMEN_FISCAL_CHOICES,
                })

            # 3) Guardar cabecera
            salida = form.save(commit=False)
            salida.almacen = almacen
            salida.save()

            # deletes (en create casi no aplica, pero correcto)
            for obj in getattr(formset, "deleted_objects", []):
                obj.delete()

            # 4) Guardar detalles
            for d in detalles_validos:
                d.salida = salida
                d.save()

            # 5) Descontar stock en lote por producto
            aplicar_movimientos_salida(almacen_id=almacen.id, requeridos=requeridos)

            messages.success(request, "Salida por venta creada correctamente.")
            return redirect("salidas_list")

        messages.error(request, "Revisa los datos. Hay campos inválidos.")

    else:
        form = SalidaVentaForm(initial={
            "folio": next_folio_movimiento(tipo="VTA", width=6),
            "fecha": timezone.localdate(),
        })
        formset = DetalleFormSet(queryset=SalidaInventarioDetalle.objects.none())

    return render(request, "inventarios/salida_venta_form.html", {
        "form": form,
        "formset": formset,
        "productos": productos,
        "clientes": clientes,
        "almacenes": almacenes_qs,
        "almacen": almacen,
        "REGIMEN_FISCAL_CHOICES": REGIMEN_FISCAL_CHOICES,
    })

@transaction.atomic
def salida_proyecto_create(request):
    almacenes_qs = Almacen.objects.filter(es_activo=True).order_by("tipo", "nombre")

    almacen_default = get_almacen_default()
    almacen = almacen_default or almacenes_qs.first()
    if not almacen:
        messages.error(request, "No hay almacenes activos.")
        return redirect("almacenes_create")

    DetalleFormSet = modelformset_factory(
        SalidaInventarioDetalle,
        form=SalidaInventarioDetalleForm,
        extra=0,
        can_delete=False,
    )

    if request.method == "POST":
        almacen_id = (request.POST.get("almacen_id") or "").strip()
        if almacen_id.isdigit():
            almacen = almacenes_qs.filter(id=int(almacen_id)).first() or almacen

        form = SalidaProyectoForm(request.POST)
        formset = DetalleFormSet(request.POST, queryset=SalidaInventarioDetalle.objects.none())

        if not form.is_valid() or not formset.is_valid():
            messages.error(request, "Revisa los datos capturados.")
            return render(request, "inventarios/salida_proyecto_form.html", {
                "form": form,
                "formset": formset,
                "almacenes": almacenes_qs,
                "almacen": almacen,
            })

        # 1) Validar que exista al menos un producto válido
        detalles_validos = []
        for f in formset:
            cd = getattr(f, "cleaned_data", None)
            if not cd:
                continue

            producto = cd.get("producto")
            cantidad = cd.get("cantidad") or 0
            precio = cd.get("precio_unitario")

            if producto and cantidad > 0:
                detalles_validos.append({
                    "producto": producto,
                    "cantidad": cantidad,
                    "precio": precio,
                })

        if not detalles_validos:
            messages.error(request, "Agrega al menos un producto con cantidad mayor a 0.")
            return render(request, "inventarios/salida_proyecto_form.html", {
                "form": form,
                "formset": formset,
                "almacenes": almacenes_qs,
                "almacen": almacen,
            })

        # 2) Validar productos duplicados (si quieres mantener esta regla)
        seen = set()
        duplicados = set()
        for d in detalles_validos:
            pid = d["producto"].id
            if pid in seen:
                duplicados.add(d["producto"])
            seen.add(pid)

        if duplicados:
            messages.error(
                request,
                "No puedes repetir productos en el detalle: " + ", ".join([str(p) for p in duplicados])
            )
            return render(request, "inventarios/salida_proyecto_form.html", {
                "form": form,
                "formset": formset,
                "almacenes": almacenes_qs,
                "almacen": almacen,
            })

        # 3) Validar stock (sumando por producto)
        requeridos = agrupar_requeridos_por_producto(
            (d["producto"].id, d["cantidad"]) for d in detalles_validos
        )

        productos_por_id = {
            p.id: str(p)
            for p in Producto.objects.filter(id__in=requeridos.keys())
        }

        ok, disponibles, faltantes = validar_stock_suficiente(
            almacen_id=almacen.id,
            requeridos=requeridos,
        )

        if not ok:
            for msg in errores_stock_humano(
                almacen_nombre=str(almacen),
                faltantes=faltantes,
                disponibles=disponibles,
                productos_por_id=productos_por_id,
            ):
                messages.error(request, msg)

            return render(request, "inventarios/salida_proyecto_form.html", {
                "form": form,
                "formset": formset,
                "almacenes": almacenes_qs,
                "almacen": almacen,
            })

        # 4) Guardar cabecera
        salida = form.save(commit=False)
        salida.almacen = almacen
        salida.save()

        # 5) Guardar detalles
        for d in detalles_validos:
            SalidaInventarioDetalle.objects.create(
                salida=salida,
                producto=d["producto"],
                cantidad=d["cantidad"],
                precio_unitario=d["precio"],
            )

        # 6) Descontar stock en lote por producto
        aplicar_movimientos_salida(almacen_id=almacen.id, requeridos=requeridos)

        messages.success(request, "Salida por proyecto registrada correctamente.")
        return redirect("salidas_list")

    # GET
    form = SalidaProyectoForm(initial={
        "folio": next_folio_movimiento(tipo="PRY", width=6),
        "fecha": timezone.localdate(),
    })

    formset = DetalleFormSet(queryset=SalidaInventarioDetalle.objects.none())

    return render(request, "inventarios/salida_proyecto_form.html", {
        "form": form,
        "formset": formset,
        "almacenes": almacenes_qs,
        "almacen": almacen,
    })