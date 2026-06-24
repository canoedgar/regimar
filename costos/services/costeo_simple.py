from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from catalogos.models import Almacen, Producto
from inventarios.models import InventarioStock
from ventas.models import NotaVenta, NotaVentaDetalle

from costos.models import (
    AlmacenajeProductoPeriodo,
    GastoPeriodo,
    PeriodoCosteo,
    ResultadoCostoProducto,
)

CENTAVOS = Decimal("0.01")
CUATRO_DECIMALES = Decimal("0.0001")
SEIS_DECIMALES = Decimal("0.000001")
CIEN = Decimal("100")


@dataclass
class ResumenGeneracionCosteo:
    periodo: PeriodoCosteo
    total_productos: int
    total_ventas: Decimal
    total_costo_compra: Decimal
    total_gastos_operativos: Decimal
    total_almacenaje: Decimal
    total_costo_real: Decimal
    utilidad_real: Decimal
    margen_real: Decimal
    total_almacenes_calculados: int
    total_productos_almacenaje: int
    advertencias: list[str]


def generar_costeo_periodo(periodo: PeriodoCosteo, usuario=None) -> ResumenGeneracionCosteo:
    """
    Regenera almacenaje y resultado por producto del flujo simple.
    No modifica inventario, costo promedio ni precio de productos.
    """
    if not periodo.puede_generarse:
        raise ValidationError("Solo se pueden generar costos en periodos abiertos o en revisión.")

    with transaction.atomic():
        periodo.almacenajes.all().delete()
        periodo.resultados.all().delete()

        almacenajes, advertencias = _calcular_almacenaje(periodo)
        if almacenajes:
            AlmacenajeProductoPeriodo.objects.bulk_create(almacenajes)

        resultados = _calcular_resultados(periodo)
        if resultados:
            ResultadoCostoProducto.objects.bulk_create(resultados)

        periodo.estado = PeriodoCosteo.ESTADO_REVISION
        periodo.save(update_fields=["estado", "actualizado_en"])

    return obtener_resumen_periodo(periodo, advertencias=advertencias)


def cerrar_costeo_periodo(periodo: PeriodoCosteo, usuario=None):
    if not periodo.resultados.exists():
        raise ValidationError("Genera el costeo antes de cerrar el periodo.")
    with transaction.atomic():
        ResultadoCostoProducto.objects.filter(periodo=periodo).update(
            aprobado=True,
            aprobado_por=usuario if getattr(usuario, "is_authenticated", False) else None,
            aprobado_en=timezone.now(),
        )
        periodo.cerrar(usuario)


def obtener_resumen_periodo(periodo: PeriodoCosteo, advertencias=None) -> ResumenGeneracionCosteo:
    resultados = periodo.resultados.all()
    totales = resultados.aggregate(
        total_productos=Count("id"),
        total_ventas=Sum("venta_total"),
        total_costo_compra=Sum("costo_compra_total"),
        total_gastos_operativos=Sum("gastos_operativos"),
        total_almacenaje=Sum("costo_almacenaje"),
        total_costo_real=Sum("costo_real_total"),
        utilidad_real=Sum("utilidad_real"),
    )
    total_ventas = _q2(totales["total_ventas"] or Decimal("0"))
    utilidad_real = _q2(totales["utilidad_real"] or Decimal("0"))
    total_almacenes = periodo.almacenajes.values("almacen_id").distinct().count()
    total_productos_almacenaje = periodo.almacenajes.values("producto_id").distinct().count()

    return ResumenGeneracionCosteo(
        periodo=periodo,
        total_productos=totales["total_productos"] or 0,
        total_ventas=total_ventas,
        total_costo_compra=_q2(totales["total_costo_compra"] or Decimal("0")),
        total_gastos_operativos=_q2(totales["total_gastos_operativos"] or Decimal("0")),
        total_almacenaje=_q2(totales["total_almacenaje"] or Decimal("0")),
        total_costo_real=_q2(totales["total_costo_real"] or Decimal("0")),
        utilidad_real=utilidad_real,
        margen_real=_q2((utilidad_real / total_ventas) * CIEN) if total_ventas > 0 else Decimal("0.00"),
        total_almacenes_calculados=total_almacenes,
        total_productos_almacenaje=total_productos_almacenaje,
        advertencias=advertencias or [],
    )


def _calcular_almacenaje(periodo: PeriodoCosteo):
    advertencias = []
    almacenajes = []

    almacenes = Almacen.objects.filter(es_activo=True, es_arrendado=True)
    almacenes_por_kg = almacenes.filter(tipo_costo=Almacen.TipoCosto.POR_KILO, costo_almacen__gt=0)
    almacenes_tarima = almacenes.filter(tipo_costo=Almacen.TipoCosto.POR_TARIMA, costo_almacen__gt=0)

    if almacenes_tarima.exists():
        advertencias.append(
            "Existen almacenes configurados por tarima. En esta fase inicial solo se calcula automáticamente el almacenaje por kilo."
        )

    stocks = (
        InventarioStock.objects.select_related("producto", "almacen")
        .filter(almacen__in=almacenes_por_kg, cantidad__gt=0)
        .order_by("almacen__nombre", "producto__nombre")
    )

    for stock in stocks.iterator():
        kg = _q4(stock.cantidad)
        tarifa = _q6(stock.almacen.costo_almacen or Decimal("0"))
        importe = _q2(kg * tarifa)
        if importe <= 0:
            continue
        almacenajes.append(
            AlmacenajeProductoPeriodo(
                periodo=periodo,
                almacen=stock.almacen,
                producto=stock.producto,
                kg_al_corte=kg,
                tarifa_kg=tarifa,
                importe=importe,
                observaciones=(
                    "Calculado con el stock actual al momento de generar el costeo. "
                    f"Fecha de corte configurada: {periodo.fecha_corte_almacen:%Y-%m-%d}."
                ),
            )
        )

    gastos_almacenaje = GastoPeriodo.objects.filter(
        periodo=periodo,
        estado=GastoPeriodo.ESTADO_ACTIVO,
        tipo_gasto=GastoPeriodo.TIPO_ALMACENAJE,
        importe__gt=0,
    )
    if gastos_almacenaje.exists():
        almacenajes.extend(_distribuir_gastos_almacenaje_manual(periodo, gastos_almacenaje, almacenajes))

    if not almacenajes:
        advertencias.append("No se encontró almacenaje por kg para este periodo. Revisa almacenes arrendados, tarifa y stock actual.")

    return almacenajes, advertencias


def _distribuir_gastos_almacenaje_manual(periodo, gastos_almacenaje, almacenajes_base):
    # Distribuye gastos capturados como almacenaje usando los kg al corte existentes.
    # Si todavía no hay base de almacenes arrendados, usa todo el stock actual positivo.
    base_por_producto = defaultdict(lambda: Decimal("0"))
    for item in almacenajes_base:
        base_por_producto[item.producto_id] += _decimal(item.kg_al_corte)

    if not base_por_producto:
        for stock in InventarioStock.objects.filter(cantidad__gt=0).iterator():
            base_por_producto[stock.producto_id] += _decimal(stock.cantidad)

    total_base = sum(base_por_producto.values(), Decimal("0"))
    total_gasto = sum((_decimal(gasto.importe) for gasto in gastos_almacenaje), Decimal("0"))
    if total_base <= 0 or total_gasto <= 0:
        return []

    detalles = []
    importe_acumulado = Decimal("0.00")
    productos = list(sorted(base_por_producto.items()))
    for indice, (producto_id, kg) in enumerate(productos):
        if indice == len(productos) - 1:
            importe = _q2(total_gasto - importe_acumulado)
        else:
            importe = _q2(total_gasto * kg / total_base)
            importe_acumulado += importe
        if importe <= 0:
            continue
        detalles.append(
            AlmacenajeProductoPeriodo(
                periodo=periodo,
                almacen_id=None,
                producto_id=producto_id,
                kg_al_corte=_q4(kg),
                tarifa_kg=_q6(importe / kg) if kg > 0 else Decimal("0.000000"),
                importe=importe,
                observaciones="Distribución de gastos capturados como almacenaje manual del periodo.",
            )
        )
    return detalles


def _calcular_resultados(periodo: PeriodoCosteo):
    productos = defaultdict(_AcumuladoResultado)

    ventas = (
        NotaVentaDetalle.objects.select_related("salida", "producto")
        .filter(
            salida__tipo=NotaVenta.TIPO_VENTA,
            salida__estado=NotaVenta.ESTADO_ACTIVA,
            salida__fecha__gte=periodo.fecha_inicio,
            salida__fecha__lte=periodo.fecha_fin,
            cantidad__gt=0,
        )
        .order_by("producto__nombre")
    )

    for detalle in ventas.iterator():
        item = productos[detalle.producto_id]
        cantidad = _decimal(detalle.cantidad)
        venta_total = cantidad * _decimal(detalle.precio_unitario)
        costo_compra = cantidad * _decimal(detalle.costo_unitario_aplicado)
        item.kg_vendidos += cantidad
        item.venta_total += venta_total
        item.costo_compra_total += costo_compra

    _asignar_gastos_operativos(periodo, productos)

    almacenajes = periodo.almacenajes.values("producto_id").annotate(kg=Sum("kg_al_corte"), importe=Sum("importe"))
    for row in almacenajes:
        item = productos[row["producto_id"]]
        item.kg_almacenados += _decimal(row["kg"])
        item.costo_almacenaje += _decimal(row["importe"])

    productos_map = Producto.objects.in_bulk(list(productos.keys()))
    resultados = []
    for producto_id, item in sorted(productos.items(), key=lambda par: productos_map.get(par[0]).nombre if productos_map.get(par[0]) else ""):
        producto = productos_map.get(producto_id)
        if not producto:
            continue

        kg_vendidos = _q4(item.kg_vendidos)
        kg_almacenados = _q4(item.kg_almacenados)
        venta_total = _q2(item.venta_total)
        costo_compra_total = _q2(item.costo_compra_total)
        gastos_operativos = _q2(item.gastos_operativos)
        costo_almacenaje = _q2(item.costo_almacenaje)
        costo_real_total = _q2(costo_compra_total + gastos_operativos + costo_almacenaje)
        utilidad_real = _q2(venta_total - costo_real_total)
        margen_real = _q2((utilidad_real / venta_total) * CIEN) if venta_total > 0 else Decimal("0.00")

        costo_compra_unitario = _q6(costo_compra_total / kg_vendidos) if kg_vendidos > 0 else _q6(producto.costo_promedio or producto.ultimo_costo_compra or 0)
        gasto_unitario = _q6(gastos_operativos / kg_vendidos) if kg_vendidos > 0 else Decimal("0.000000")
        base_almacenaje_unitario = kg_vendidos if kg_vendidos > 0 else kg_almacenados
        almacenaje_unitario = _q6(costo_almacenaje / base_almacenaje_unitario) if base_almacenaje_unitario > 0 else Decimal("0.000000")
        costo_real_unitario = _q6(costo_real_total / kg_vendidos) if kg_vendidos > 0 else _q6(costo_compra_unitario + almacenaje_unitario)
        costo_sugerido = _q6(costo_compra_unitario + gasto_unitario + almacenaje_unitario)

        resultados.append(
            ResultadoCostoProducto(
                periodo=periodo,
                producto=producto,
                kg_vendidos=kg_vendidos,
                kg_almacenados=kg_almacenados,
                venta_total=venta_total,
                costo_compra_total=costo_compra_total,
                gastos_operativos=gastos_operativos,
                costo_almacenaje=costo_almacenaje,
                costo_real_total=costo_real_total,
                costo_real_unitario=costo_real_unitario,
                utilidad_real=utilidad_real,
                margen_real=margen_real,
                costo_sugerido_siguiente=costo_sugerido,
            )
        )

    return resultados


def _asignar_gastos_operativos(periodo: PeriodoCosteo, productos):
    gastos = GastoPeriodo.objects.filter(
        periodo=periodo,
        estado=GastoPeriodo.ESTADO_ACTIVO,
        importe__gt=0,
    ).exclude(tipo_gasto=GastoPeriodo.TIPO_ALMACENAJE)

    total_gastos_kg = Decimal("0")
    total_gastos_importe = Decimal("0")
    for gasto in gastos.iterator():
        if gasto.tipo_gasto == GastoPeriodo.TIPO_ADMINISTRATIVO:
            total_gastos_importe += _decimal(gasto.importe)
        else:
            total_gastos_kg += _decimal(gasto.importe)

    if total_gastos_kg > 0:
        total_kg = sum((item.kg_vendidos for item in productos.values()), Decimal("0"))
        if total_kg > 0:
            _distribuir_importe(productos, total_gastos_kg, total_kg, "kg_vendidos")

    if total_gastos_importe > 0:
        total_ventas = sum((item.venta_total for item in productos.values()), Decimal("0"))
        if total_ventas > 0:
            _distribuir_importe(productos, total_gastos_importe, total_ventas, "venta_total")


def _distribuir_importe(productos, importe_total, total_base, campo_base):
    pares = [(producto_id, getattr(item, campo_base)) for producto_id, item in productos.items() if getattr(item, campo_base) > 0]
    importe_acumulado = Decimal("0.00")
    for indice, (producto_id, base) in enumerate(pares):
        if indice == len(pares) - 1:
            asignado = _q2(importe_total - importe_acumulado)
        else:
            asignado = _q2(importe_total * base / total_base)
            importe_acumulado += asignado
        productos[producto_id].gastos_operativos += asignado


class _AcumuladoResultado:
    def __init__(self):
        self.kg_vendidos = Decimal("0")
        self.kg_almacenados = Decimal("0")
        self.venta_total = Decimal("0")
        self.costo_compra_total = Decimal("0")
        self.gastos_operativos = Decimal("0")
        self.costo_almacenaje = Decimal("0")


def _decimal(valor) -> Decimal:
    return Decimal(valor or 0)


def _q2(valor) -> Decimal:
    return Decimal(valor or 0).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _q4(valor) -> Decimal:
    return Decimal(valor or 0).quantize(CUATRO_DECIMALES, rounding=ROUND_HALF_UP)


def _q6(valor) -> Decimal:
    return Decimal(valor or 0).quantize(SEIS_DECIMALES, rounding=ROUND_HALF_UP)
