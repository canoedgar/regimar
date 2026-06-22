from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q

from catalogos.models import Producto
from inventarios.models import SalidaInventario, SalidaInventarioDetalle

from costos.models import CierreCosteoPeriodo, CierreCosteoProducto, CategoriaGasto, Gasto, GastoDistribucion

CENTAVOS = Decimal("0.01")
CUATRO_DECIMALES = Decimal("0.0001")
SEIS_DECIMALES = Decimal("0.000001")
PORCENTAJE = Decimal("0.01")
CIEN = Decimal("100")


@dataclass
class ResumenCosteoProducto:
    producto: Producto
    cantidad_vendida: Decimal
    venta_total: Decimal
    costo_compra_total: Decimal
    gasto_asignado_total: Decimal
    costo_real_total: Decimal
    utilidad_bruta: Decimal
    utilidad_real: Decimal
    precio_promedio: Decimal
    costo_compra_unitario: Decimal
    gasto_unitario: Decimal
    costo_real_unitario: Decimal
    margen_bruto_porcentaje: Decimal
    margen_real_porcentaje: Decimal
    movimientos_venta: int


@dataclass
class TotalesCosteoPeriodo:
    total_productos: int
    total_movimientos_venta: int
    total_ventas: Decimal
    total_costo_compra: Decimal
    total_gastos_distribuidos: Decimal
    total_costo_real: Decimal
    utilidad_bruta: Decimal
    utilidad_real: Decimal
    margen_bruto_porcentaje: Decimal
    margen_real_porcentaje: Decimal


@dataclass
class ResumenCosteoPeriodo:
    periodo_inicio: object
    periodo_fin: object
    productos: list[ResumenCosteoProducto]
    totales: TotalesCosteoPeriodo
    gastos_aplicados_count: int
    gastos_distribuidos_count: int
    gastos_pendientes_distribucion: list[Gasto]
    gastos_manual_sin_distribucion: list[Gasto]


class AcumuladoProducto:
    def __init__(self):
        self.cantidad_vendida = Decimal("0")
        self.venta_total = Decimal("0")
        self.costo_compra_total = Decimal("0")
        self.gasto_asignado_total = Decimal("0")
        self.movimientos_venta = 0


def calcular_resumen_costeo(periodo_inicio, periodo_fin) -> ResumenCosteoPeriodo:
    """
    Calcula la fotografía de costeo para un periodo sin guardar información.
    Usa ventas activas y distribuciones de gastos aplicados cuyo periodo queda dentro del rango solicitado.
    """
    if not periodo_inicio or not periodo_fin:
        raise ValidationError("Selecciona el periodo de costeo.")
    if periodo_inicio > periodo_fin:
        raise ValidationError("La fecha final del periodo no puede ser menor a la fecha inicial.")

    acumulados: dict[int, AcumuladoProducto] = {}

    detalles_venta = (
        SalidaInventarioDetalle.objects.select_related("salida", "producto")
        .filter(
            salida__tipo=SalidaInventario.TIPO_VENTA,
            salida__estado=SalidaInventario.ESTADO_ACTIVA,
            salida__fecha__gte=periodo_inicio,
            salida__fecha__lte=periodo_fin,
            cantidad__gt=0,
        )
        .order_by("producto__nombre", "salida__fecha")
    )

    for detalle in detalles_venta.iterator():
        item = acumulados.setdefault(detalle.producto_id, AcumuladoProducto())
        cantidad = _decimal(detalle.cantidad)
        venta_total = cantidad * _decimal(detalle.precio_unitario)
        costo_compra_total = cantidad * _decimal(detalle.costo_unitario_aplicado)

        item.cantidad_vendida += cantidad
        item.venta_total += venta_total
        item.costo_compra_total += costo_compra_total
        item.movimientos_venta += 1

    distribuciones = (
        GastoDistribucion.objects.select_related("gasto", "producto")
        .filter(
            gasto__estado=Gasto.ESTADO_APLICADO,
            gasto__periodo_inicio__gte=periodo_inicio,
            gasto__periodo_fin__lte=periodo_fin,
        )
        .order_by("producto__nombre")
    )

    gastos_distribuidos_ids = set()
    for distribucion in distribuciones.iterator():
        item = acumulados.setdefault(distribucion.producto_id, AcumuladoProducto())
        item.gasto_asignado_total += _decimal(distribucion.importe_asignado)
        gastos_distribuidos_ids.add(distribucion.gasto_id)

    producto_ids = sorted(acumulados.keys())
    productos_map = Producto.objects.in_bulk(producto_ids)
    productos_resumen: list[ResumenCosteoProducto] = []

    for producto_id in producto_ids:
        producto = productos_map.get(producto_id)
        if not producto:
            continue

        item = acumulados[producto_id]
        cantidad_vendida = _q4(item.cantidad_vendida)
        venta_total = _q2(item.venta_total)
        costo_compra_total = _q2(item.costo_compra_total)
        gasto_asignado_total = _q2(item.gasto_asignado_total)
        costo_real_total = _q2(costo_compra_total + gasto_asignado_total)
        utilidad_bruta = _q2(venta_total - costo_compra_total)
        utilidad_real = _q2(venta_total - costo_real_total)

        productos_resumen.append(
            ResumenCosteoProducto(
                producto=producto,
                cantidad_vendida=cantidad_vendida,
                venta_total=venta_total,
                costo_compra_total=costo_compra_total,
                gasto_asignado_total=gasto_asignado_total,
                costo_real_total=costo_real_total,
                utilidad_bruta=utilidad_bruta,
                utilidad_real=utilidad_real,
                precio_promedio=_q6(venta_total / cantidad_vendida) if cantidad_vendida > 0 else Decimal("0.000000"),
                costo_compra_unitario=_q6(costo_compra_total / cantidad_vendida) if cantidad_vendida > 0 else Decimal("0.000000"),
                gasto_unitario=_q6(gasto_asignado_total / cantidad_vendida) if cantidad_vendida > 0 else Decimal("0.000000"),
                costo_real_unitario=_q6(costo_real_total / cantidad_vendida) if cantidad_vendida > 0 else Decimal("0.000000"),
                margen_bruto_porcentaje=_q2((utilidad_bruta / venta_total) * CIEN) if venta_total > 0 else Decimal("0.00"),
                margen_real_porcentaje=_q2((utilidad_real / venta_total) * CIEN) if venta_total > 0 else Decimal("0.00"),
                movimientos_venta=item.movimientos_venta,
            )
        )

    total_ventas = _q2(sum((item.venta_total for item in productos_resumen), Decimal("0")))
    total_costo_compra = _q2(sum((item.costo_compra_total for item in productos_resumen), Decimal("0")))
    total_gastos_distribuidos = _q2(sum((item.gasto_asignado_total for item in productos_resumen), Decimal("0")))
    total_costo_real = _q2(total_costo_compra + total_gastos_distribuidos)
    utilidad_bruta = _q2(total_ventas - total_costo_compra)
    utilidad_real = _q2(total_ventas - total_costo_real)

    gastos_periodo = _gastos_aplicados_periodo(periodo_inicio, periodo_fin)
    gastos_pendientes = _gastos_pendientes_distribucion(gastos_periodo)
    gastos_manual = _gastos_manual_sin_distribucion(gastos_periodo)

    return ResumenCosteoPeriodo(
        periodo_inicio=periodo_inicio,
        periodo_fin=periodo_fin,
        productos=productos_resumen,
        totales=TotalesCosteoPeriodo(
            total_productos=len(productos_resumen),
            total_movimientos_venta=sum((item.movimientos_venta for item in productos_resumen), 0),
            total_ventas=total_ventas,
            total_costo_compra=total_costo_compra,
            total_gastos_distribuidos=total_gastos_distribuidos,
            total_costo_real=total_costo_real,
            utilidad_bruta=utilidad_bruta,
            utilidad_real=utilidad_real,
            margen_bruto_porcentaje=_q2((utilidad_bruta / total_ventas) * CIEN) if total_ventas > 0 else Decimal("0.00"),
            margen_real_porcentaje=_q2((utilidad_real / total_ventas) * CIEN) if total_ventas > 0 else Decimal("0.00"),
        ),
        gastos_aplicados_count=gastos_periodo.count(),
        gastos_distribuidos_count=len(gastos_distribuidos_ids),
        gastos_pendientes_distribucion=list(gastos_pendientes[:10]),
        gastos_manual_sin_distribucion=list(gastos_manual[:10]),
    )


def generar_cierre_costeo(periodo_inicio, periodo_fin, usuario=None, notas="") -> CierreCosteoPeriodo:
    """Genera y guarda el cierre congelado para el periodo indicado."""
    resumen = calcular_resumen_costeo(periodo_inicio, periodo_fin)

    if resumen.gastos_pendientes_distribucion:
        raise ValidationError(
            "Existen gastos aplicados pendientes de distribución. Recalcula o corrige esos gastos antes de cerrar el periodo."
        )

    if not resumen.productos:
        raise ValidationError("No se encontraron ventas ni gastos distribuidos para cerrar el periodo seleccionado.")

    with transaction.atomic():
        cierre = CierreCosteoPeriodo(
            periodo_inicio=periodo_inicio,
            periodo_fin=periodo_fin,
            estado=CierreCosteoPeriodo.ESTADO_CERRADO,
            total_productos=resumen.totales.total_productos,
            total_movimientos_venta=resumen.totales.total_movimientos_venta,
            total_ventas=resumen.totales.total_ventas,
            total_costo_compra=resumen.totales.total_costo_compra,
            total_gastos_distribuidos=resumen.totales.total_gastos_distribuidos,
            total_costo_real=resumen.totales.total_costo_real,
            utilidad_bruta=resumen.totales.utilidad_bruta,
            utilidad_real=resumen.totales.utilidad_real,
            margen_bruto_porcentaje=resumen.totales.margen_bruto_porcentaje,
            margen_real_porcentaje=resumen.totales.margen_real_porcentaje,
            notas=(notas or "").strip(),
            creado_por=usuario if getattr(usuario, "is_authenticated", False) else None,
        )
        cierre.full_clean()
        cierre.save()

        detalles = [
            CierreCosteoProducto(
                cierre=cierre,
                producto=item.producto,
                cantidad_vendida=item.cantidad_vendida,
                venta_total=item.venta_total,
                costo_compra_total=item.costo_compra_total,
                gasto_asignado_total=item.gasto_asignado_total,
                costo_real_total=item.costo_real_total,
                utilidad_bruta=item.utilidad_bruta,
                utilidad_real=item.utilidad_real,
                precio_promedio=item.precio_promedio,
                costo_compra_unitario=item.costo_compra_unitario,
                gasto_unitario=item.gasto_unitario,
                costo_real_unitario=item.costo_real_unitario,
                margen_bruto_porcentaje=item.margen_bruto_porcentaje,
                margen_real_porcentaje=item.margen_real_porcentaje,
                movimientos_venta=item.movimientos_venta,
            )
            for item in resumen.productos
        ]
        CierreCosteoProducto.objects.bulk_create(detalles)

    return cierre


def _gastos_aplicados_periodo(periodo_inicio, periodo_fin):
    return Gasto.objects.select_related("categoria").filter(
        estado=Gasto.ESTADO_APLICADO,
        periodo_inicio__gte=periodo_inicio,
        periodo_fin__lte=periodo_fin,
    )


def _gastos_pendientes_distribucion(gastos_qs):
    return (
        gastos_qs.filter(categoria__distribuible=True)
        .exclude(metodo_distribucion__in=[CategoriaGasto.DIST_NO_DISTRIBUIR, CategoriaGasto.DIST_MANUAL])
        .annotate(distribuciones_count=Count("distribuciones"))
        .filter(distribuciones_count=0)
        .order_by("fecha", "folio")
    )


def _gastos_manual_sin_distribucion(gastos_qs):
    return (
        gastos_qs.filter(
            categoria__distribuible=True,
            metodo_distribucion=CategoriaGasto.DIST_MANUAL,
        )
        .annotate(distribuciones_count=Count("distribuciones"))
        .filter(distribuciones_count=0)
        .order_by("fecha", "folio")
    )


def _decimal(valor) -> Decimal:
    return Decimal(valor or 0)


def _q2(valor: Decimal) -> Decimal:
    return Decimal(valor or 0).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _q4(valor: Decimal) -> Decimal:
    return Decimal(valor or 0).quantize(CUATRO_DECIMALES, rounding=ROUND_HALF_UP)


def _q6(valor: Decimal) -> Decimal:
    return Decimal(valor or 0).quantize(SEIS_DECIMALES, rounding=ROUND_HALF_UP)
