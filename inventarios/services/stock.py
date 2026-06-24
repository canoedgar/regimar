# inventarios/services/stock.py

from decimal import Decimal
from typing import Dict, Iterable, List, Tuple

from django.db import IntegrityError
from django.db.models import F

from catalogos.models import Producto

from ..models import InventarioStock
from ..utils import decimal_or_default as _to_decimal


def aplicar_movimiento_stock(*, producto_id: int, almacen_id: int, delta):
    """
    Aplica un movimiento puro de existencias.

    delta positivo = suma stock
    delta negativo = resta stock

    Este servicio solo modifica cantidades. No recalcula costos, no actualiza
    último costo de compra y no registra bitácoras comerciales.
    Requiere estar dentro de transaction.atomic si quieres locking efectivo.
    """
    delta = _to_decimal(delta)

    stock_row, _ = InventarioStock.objects.select_for_update().get_or_create(
        producto_id=producto_id,
        almacen_id=almacen_id,
        defaults={"cantidad": Decimal("0")},
    )

    actual = _to_decimal(stock_row.cantidad)
    nuevo = actual + delta

    if nuevo < 0:
        raise IntegrityError(
            f"Stock insuficiente (motor): producto_id={producto_id}, almacen_id={almacen_id}, "
            f"disponible={actual}, requerido={-delta}"
        )

    stock_row.cantidad = nuevo
    stock_row.save(update_fields=["cantidad"])

    Producto.objects.filter(pk=producto_id).update(stock=F("stock") + delta)


def agrupar_requeridos_por_producto(detalles: Iterable[tuple[int, object]]) -> Dict[int, Decimal]:
    """
    detalles: iterable de (producto_id, cantidad)
    Devuelve dict producto_id -> cantidad_total (sumando duplicados).
    """
    req: Dict[int, Decimal] = {}
    for producto_id, cantidad in detalles:
        if not producto_id:
            continue
        c = _to_decimal(cantidad)
        if c <= 0:
            continue
        req[producto_id] = req.get(producto_id, Decimal("0")) + c
    return req


def validar_stock_suficiente(
    *,
    almacen_id: int,
    requeridos: Dict[int, Decimal],
) -> Tuple[bool, Dict[int, Decimal], Dict[int, Decimal]]:
    """
    Bloquea filas de InventarioStock del almacén y compara stock vs requerido.
    Retorna:
      - ok (bool)
      - disponibles: dict producto_id -> disponible
      - faltantes: dict producto_id -> requerido (solo los que no alcanzan)
    NOTA: requiere estar dentro de transaction.atomic.
    """
    if not requeridos:
        return True, {}, {}

    rows = list(
        InventarioStock.objects
        .select_for_update()
        .filter(almacen_id=almacen_id, producto_id__in=requeridos.keys())
    )

    disponibles: Dict[int, Decimal] = {r.producto_id: _to_decimal(r.cantidad) for r in rows}

    faltantes: Dict[int, Decimal] = {}
    for pid, req in requeridos.items():
        disp = disponibles.get(pid, Decimal("0"))
        if disp < req:
            faltantes[pid] = req

    return (len(faltantes) == 0), disponibles, faltantes


def errores_stock_humano(
    *,
    almacen_nombre: str,
    faltantes: Dict[int, Decimal],
    disponibles: Dict[int, Decimal],
    productos_por_id: Dict[int, str],
) -> List[str]:
    """
    Convierte faltantes a lista de strings para messages.error.
    """
    errores: List[str] = []
    for pid, req in faltantes.items():
        nombre = productos_por_id.get(pid, f"Producto {pid}")
        disp = disponibles.get(pid, Decimal("0"))
        errores.append(
            f"Stock insuficiente para '{nombre}'. Disponible en {almacen_nombre}: {disp} | Requerido: {req}"
        )
    return errores


def aplicar_movimientos_salida(*, almacen_id: int, requeridos: Dict[int, Decimal]):
    """
    Descuenta stock en lote por producto (delta negativo).
    Asume que YA validaste stock suficiente para ese almacén.
    """
    for pid, qty in (requeridos or {}).items():
        qty = _to_decimal(qty)
        if qty > 0:
            aplicar_movimiento_stock(producto_id=pid, almacen_id=almacen_id, delta=-qty)


def aplicar_movimientos_entrada(*, almacen_id: int, agregados: Dict[int, Decimal]):
    """
    Suma stock en lote por producto (delta positivo).
    """
    for pid, qty in (agregados or {}).items():
        qty = _to_decimal(qty)
        if qty > 0:
            aplicar_movimiento_stock(producto_id=pid, almacen_id=almacen_id, delta=qty)
