import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from catalogos.models import Cliente, ParametroSistema, Producto
from catalogos.services.clientes_precios import registrar_ultimo_precio_cliente
from .models import CotizacionPrecio, CotizacionPrecioDetalle


ZERO = Decimal("0.00")
Q2 = Decimal("0.01")
Q0 = Decimal("1")


def money(value):
    return to_decimal(value).quantize(Q2, rounding=ROUND_HALF_UP)


def entero(value):
    return to_decimal(value).quantize(Q0, rounding=ROUND_HALF_UP)


def to_decimal(value, default=ZERO):
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def fecha_vigencia_default():
    dias = ParametroSistema.get_int("PRECIO_VIGENCIA_COTIZACIONES", 30)
    return timezone.localdate() + timedelta(days=dias)


def next_folio_cotizacion():
    year = timezone.localdate().year
    prefix = f"COT-{year}-"
    last = CotizacionPrecio.objects.filter(folio__startswith=prefix).order_by("-id").first()
    if not last:
        return f"{prefix}0001"
    try:
        consecutivo = int(str(last.folio).split("-")[-1]) + 1
    except (ValueError, IndexError):
        consecutivo = last.id + 1
    return f"{prefix}{consecutivo:04d}"


def calcular_margenes(*, costo_base, precio_propuesto, cantidad_estimada=1):
    costo = money(costo_base)
    precio = entero(precio_propuesto)
    cantidad = to_decimal(cantidad_estimada, Decimal("1"))
    if cantidad <= 0:
        cantidad = Decimal("1")

    utilidad_unitaria = entero(precio - costo)
    if costo > 0:
        margen_porcentaje = entero(((precio - costo) / costo) * Decimal("100"))
    else:
        margen_porcentaje = Decimal("0")

    return {
        "precio_propuesto": money(precio),
        "utilidad_unitaria": money(utilidad_unitaria),
        "margen_porcentaje": money(margen_porcentaje),
        "importe_estimado": money(precio * cantidad),
        "utilidad_total_estimada": money(utilidad_unitaria * cantidad),
    }


def normalizar_detalles_payload(detalles_payload):
    if isinstance(detalles_payload, str):
        detalles_payload = json.loads(detalles_payload or "[]")
    if not isinstance(detalles_payload, list):
        raise ValueError("El listado de productos no es válido.")

    producto_ids = [int(item.get("producto_id")) for item in detalles_payload if str(item.get("producto_id", "")).isdigit()]
    productos = Producto.objects.in_bulk(producto_ids)
    detalles = []
    vistos = set()

    for item in detalles_payload:
        producto_id = int(item.get("producto_id") or 0)
        if producto_id in vistos:
            continue
        producto = productos.get(producto_id)
        if not producto:
            continue
        vistos.add(producto_id)

        cantidad_estimada = to_decimal(item.get("cantidad_estimada"), Decimal("1"))
        if cantidad_estimada <= 0:
            cantidad_estimada = Decimal("1")

        cantidad_cajas = to_decimal(item.get("cantidad_cajas"), None)
        costo_base = money(item.get("costo_base") or producto.costo_promedio or producto.ultimo_costo_compra or 0)
        precio_sugerido = money(item.get("precio_sugerido") or producto.precio or 0)
        precio_minimo = money(item.get("precio_minimo") or producto.precio_minimo or 0)
        precio_propuesto = entero(item.get("precio_propuesto") or precio_sugerido)
        calculos = calcular_margenes(costo_base=costo_base, precio_propuesto=precio_propuesto, cantidad_estimada=cantidad_estimada)

        detalles.append({
            "producto": producto,
            "cantidad_estimada": money(cantidad_estimada),
            "cantidad_cajas": money(cantidad_cajas) if cantidad_cajas is not None else None,
            "costo_base": costo_base,
            "precio_sugerido": precio_sugerido,
            "precio_minimo": precio_minimo,
            "precio_propuesto": calculos["precio_propuesto"],
            "margen_porcentaje": calculos["margen_porcentaje"],
            "utilidad_unitaria": calculos["utilidad_unitaria"],
            "importe_estimado": calculos["importe_estimado"],
            "utilidad_total_estimada": calculos["utilidad_total_estimada"],
            "unidad_precio": (producto.metrica or "KG").upper(),
            "requiere_autorizacion": precio_minimo > 0 and calculos["precio_propuesto"] < precio_minimo,
            "observaciones": str(item.get("observaciones") or "")[:255],
        })

    if not detalles:
        raise ValueError("Selecciona al menos un producto para la cotización.")
    return detalles


@transaction.atomic
def guardar_cotizacion(*, form, detalles_payload, usuario):
    detalles = normalizar_detalles_payload(detalles_payload)
    cotizacion = form.save(commit=False)
    if not cotizacion.pk:
        cotizacion.folio = next_folio_cotizacion()
        cotizacion.creado_por = usuario
    cotizacion.estatus = CotizacionPrecio.ESTATUS_BORRADOR
    cotizacion.save()

    cotizacion.detalles.all().delete()
    CotizacionPrecioDetalle.objects.bulk_create([
        CotizacionPrecioDetalle(cotizacion=cotizacion, **detalle)
        for detalle in detalles
    ])
    return cotizacion


@transaction.atomic
def aprobar_cotizacion(*, cotizacion, usuario):
    cotizacion.marcar_vencida_si_aplica(guardar=True)
    if cotizacion.estatus == CotizacionPrecio.ESTATUS_VENCIDA:
        raise ValueError("No se puede aprobar una cotización vencida.")
    if cotizacion.estatus == CotizacionPrecio.ESTATUS_CANCELADA:
        raise ValueError("No se puede aprobar una cotización cancelada.")
    if not cotizacion.cliente_id:
        raise ValueError("La cotización debe tener un cliente del sistema para aprobarse.")

    for detalle in cotizacion.detalles.select_related("producto"):
        registrar_ultimo_precio_cliente(
            cliente=cotizacion.cliente,
            producto=detalle.producto,
            precio=detalle.precio_propuesto,
            usuario=usuario,
            observaciones=f"Cotización aprobada {cotizacion.folio}",
        )

    cotizacion.estatus = CotizacionPrecio.ESTATUS_APROBADA
    cotizacion.autorizado_por = usuario
    cotizacion.fecha_autorizacion = timezone.now()
    cotizacion.save(update_fields=["estatus", "autorizado_por", "fecha_autorizacion", "updated_at"])
    return cotizacion


@transaction.atomic
def cancelar_cotizacion(*, cotizacion):
    if cotizacion.estatus == CotizacionPrecio.ESTATUS_APROBADA:
        raise ValueError("No se puede cancelar una cotización aprobada.")
    cotizacion.estatus = CotizacionPrecio.ESTATUS_CANCELADA
    cotizacion.save(update_fields=["estatus", "updated_at"])
    return cotizacion
