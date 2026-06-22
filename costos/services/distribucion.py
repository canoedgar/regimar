from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from inventarios.models import EntradaInventario, EntradaInventarioDetalle, SalidaInventario, SalidaInventarioDetalle

from costos.models import CategoriaGasto, Gasto, GastoDistribucion

CENTAVOS = Decimal("0.01")
SEIS_DECIMALES = Decimal("0.000001")
CUATRO_DECIMALES = Decimal("0.0001")
CIEN = Decimal("100")


@dataclass(frozen=True)
class BaseDistribucion:
    producto_id: int
    almacen_id: int | None
    cantidad_base: Decimal


def distribuir_gasto(gasto: Gasto):
    """
    Regenera la distribución automática de un gasto aplicado.

    La distribución es un snapshot: elimina la distribución previa del gasto y crea
    nuevas líneas según el método configurado. No modifica inventario ni ventas.
    """
    if gasto.estado != Gasto.ESTADO_APLICADO:
        raise ValidationError("Solo se pueden distribuir gastos aplicados.")

    with transaction.atomic():
        gasto.distribuciones.all().delete()

        if not _requiere_distribucion_automatica(gasto):
            return []

        bases = _obtener_bases_distribucion(gasto)
        if not bases:
            raise ValidationError(_mensaje_sin_base(gasto))

        total_base = sum((base.cantidad_base for base in bases), Decimal("0"))
        if total_base <= 0:
            raise ValidationError(_mensaje_sin_base(gasto))

        distribuciones = _crear_distribuciones(gasto, bases, total_base)
        if distribuciones:
            GastoDistribucion.objects.bulk_create(distribuciones)

        return distribuciones


def revertir_distribucion_gasto(gasto: Gasto):
    """Elimina la distribución snapshot de un gasto sin tocar movimientos de inventario."""
    return gasto.distribuciones.all().delete()


def _requiere_distribucion_automatica(gasto: Gasto) -> bool:
    if not getattr(gasto.categoria, "distribuible", False):
        return False
    return gasto.metodo_distribucion not in {
        CategoriaGasto.DIST_NO_DISTRIBUIR,
        CategoriaGasto.DIST_MANUAL,
    }


def _obtener_bases_distribucion(gasto: Gasto) -> list[BaseDistribucion]:
    metodo = gasto.metodo_distribucion

    if metodo in {CategoriaGasto.DIST_KG_VENDIDO, CategoriaGasto.DIST_IMPORTE_VENTA}:
        return _bases_ventas(gasto, usar_importe=metodo == CategoriaGasto.DIST_IMPORTE_VENTA)

    if metodo in {CategoriaGasto.DIST_KG_COMPRADO, CategoriaGasto.DIST_COSTO_COMPRA}:
        return _bases_compras(gasto, usar_costo=metodo == CategoriaGasto.DIST_COSTO_COMPRA)

    if metodo == CategoriaGasto.DIST_DIRECTO_ENTRADA:
        return _bases_directo_entrada(gasto)

    return []


def _bases_ventas(gasto: Gasto, usar_importe: bool) -> list[BaseDistribucion]:
    detalles = (
        SalidaInventarioDetalle.objects.select_related("salida", "producto", "almacen", "salida__almacen")
        .filter(
            salida__tipo=SalidaInventario.TIPO_VENTA,
            salida__estado=SalidaInventario.ESTADO_ACTIVA,
            salida__fecha__gte=gasto.periodo_inicio,
            salida__fecha__lte=gasto.periodo_fin,
            cantidad__gt=0,
        )
    )

    if gasto.almacen_id:
        detalles = detalles.filter(Q(almacen_id=gasto.almacen_id) | Q(almacen_id__isnull=True, salida__almacen_id=gasto.almacen_id))

    acumulado: dict[tuple[int, int | None], Decimal] = defaultdict(lambda: Decimal("0"))
    for detalle in detalles.iterator():
        almacen_id = detalle.almacen_id or detalle.salida.almacen_id
        cantidad = Decimal(detalle.cantidad or 0)
        if usar_importe:
            base = cantidad * Decimal(detalle.precio_unitario or 0)
        else:
            base = cantidad
        if base > 0:
            acumulado[(detalle.producto_id, almacen_id)] += base

    return _normalizar_bases(acumulado)


def _bases_compras(gasto: Gasto, usar_costo: bool) -> list[BaseDistribucion]:
    detalles = (
        EntradaInventarioDetalle.objects.select_related("entrada", "producto", "almacen", "entrada__almacen")
        .filter(
            entrada__tipo__in=[EntradaInventario.TIPO_OC_CON_FACTURA, EntradaInventario.TIPO_ENTRADA_MANUAL],
            entrada__fecha__gte=gasto.periodo_inicio,
            entrada__fecha__lte=gasto.periodo_fin,
            cantidad__gt=0,
        )
    )

    if gasto.almacen_id:
        detalles = detalles.filter(Q(almacen_id=gasto.almacen_id) | Q(almacen_id__isnull=True, entrada__almacen_id=gasto.almacen_id))

    acumulado: dict[tuple[int, int | None], Decimal] = defaultdict(lambda: Decimal("0"))
    for detalle in detalles.iterator():
        almacen_id = detalle.almacen_id or detalle.entrada.almacen_id
        cantidad = Decimal(detalle.cantidad or 0)
        if usar_costo:
            costo_total = Decimal(detalle.costo_total or 0)
            base = costo_total if costo_total > 0 else cantidad * Decimal(detalle.costo_unitario or 0)
        else:
            base = cantidad
        if base > 0:
            acumulado[(detalle.producto_id, almacen_id)] += base

    return _normalizar_bases(acumulado)


def _bases_directo_entrada(gasto: Gasto) -> list[BaseDistribucion]:
    if not gasto.entrada_inventario_id:
        raise ValidationError("Selecciona la entrada de inventario relacionada para distribuir directo a entrada.")

    detalles = (
        EntradaInventarioDetalle.objects.select_related("entrada", "producto", "almacen", "entrada__almacen")
        .filter(entrada_id=gasto.entrada_inventario_id, cantidad__gt=0)
    )

    acumulado: dict[tuple[int, int | None], Decimal] = defaultdict(lambda: Decimal("0"))
    for detalle in detalles.iterator():
        almacen_id = detalle.almacen_id or detalle.entrada.almacen_id
        if gasto.almacen_id and almacen_id != gasto.almacen_id:
            continue
        cantidad = Decimal(detalle.cantidad or 0)
        if cantidad > 0:
            acumulado[(detalle.producto_id, almacen_id)] += cantidad

    return _normalizar_bases(acumulado)


def _normalizar_bases(acumulado: dict[tuple[int, int | None], Decimal]) -> list[BaseDistribucion]:
    bases = [
        BaseDistribucion(producto_id=producto_id, almacen_id=almacen_id, cantidad_base=_q4(cantidad_base))
        for (producto_id, almacen_id), cantidad_base in acumulado.items()
        if cantidad_base > 0
    ]
    return sorted(bases, key=lambda item: (item.producto_id, item.almacen_id or 0))


def _crear_distribuciones(gasto: Gasto, bases: list[BaseDistribucion], total_base: Decimal) -> list[GastoDistribucion]:
    distribuciones: list[GastoDistribucion] = []
    importe_total = _q2(Decimal(gasto.importe or 0))
    importe_acumulado = Decimal("0.00")

    for indice, base in enumerate(bases):
        if indice == len(bases) - 1:
            importe_asignado = importe_total - importe_acumulado
        else:
            importe_asignado = _q2((importe_total * base.cantidad_base) / total_base)
            importe_acumulado += importe_asignado

        porcentaje = _q6((base.cantidad_base / total_base) * CIEN)
        costo_unitario = _q6(importe_asignado / base.cantidad_base) if base.cantidad_base > 0 else Decimal("0.000000")

        distribuciones.append(
            GastoDistribucion(
                gasto=gasto,
                producto_id=base.producto_id,
                almacen_id=base.almacen_id,
                metodo_distribucion=gasto.metodo_distribucion,
                cantidad_base=base.cantidad_base,
                porcentaje=porcentaje,
                importe_asignado=importe_asignado,
                costo_unitario_asignado=costo_unitario,
            )
        )

    return distribuciones


def _mensaje_sin_base(gasto: Gasto) -> str:
    metodo = gasto.get_metodo_distribucion_display()
    return (
        f"No se encontraron movimientos base para distribuir el gasto con el método '{metodo}' "
        f"en el periodo {gasto.periodo_inicio:%Y-%m-%d} a {gasto.periodo_fin:%Y-%m-%d}."
    )


def _q2(valor: Decimal) -> Decimal:
    return Decimal(valor or 0).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _q4(valor: Decimal) -> Decimal:
    return Decimal(valor or 0).quantize(CUATRO_DECIMALES, rounding=ROUND_HALF_UP)


def _q6(valor: Decimal) -> Decimal:
    return Decimal(valor or 0).quantize(SEIS_DECIMALES, rounding=ROUND_HALF_UP)
