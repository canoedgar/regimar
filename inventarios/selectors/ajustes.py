from decimal import Decimal

from catalogos.models import ParametroSistema, ProductoMetricaConversion

from ..models import EntradaInventario, SalidaInventario
from ..services.reversas import ReversaInventarioService
from ..utils import decimal_or_default as _to_decimal, decimal_text as _decimal_texto


def _parametro_decimal(clave, default="0"):
    parametro = ParametroSistema.objects.filter(clave=clave, activo=True).first()
    if not parametro:
        return Decimal(str(default))
    return _to_decimal(parametro.valor, default=default)


def conversion_ajuste_reciente(producto, cantidad):
    """
    Calcula la conversión visual para ajustes recientes.

    La cantidad del detalle ya está guardada en la métrica base del producto;
    este cálculo solo es informativo para mostrar cajas/presentaciones.
    """
    cantidad = _to_decimal(cantidad)
    if not producto or cantidad <= 0:
        return {
            "cantidad": None,
            "texto": "—",
            "help": "Sin producto o cantidad para convertir.",
        }

    metrica_base = getattr(producto, "metrica", None) or "kg"

    if bool(getattr(producto, "maneja_peso_variable", False)):
        factor = _parametro_decimal("ARRACHERA_PROM_CAJA", "0")
        if factor <= 0:
            return {
                "cantidad": None,
                "texto": "Sin parámetro",
                "help": "Configura ARRACHERA_PROM_CAJA para estimar cajas en productos con peso variable.",
            }

        cajas = cantidad / factor
        return {
            "cantidad": cajas,
            "texto": f"{_decimal_texto(cajas)} cajas aprox.",
            "help": f"{_decimal_texto(cantidad)} {metrica_base} / {_decimal_texto(factor)} {metrica_base} promedio por caja.",
        }

    conversion = (
        ProductoMetricaConversion.objects
        .filter(producto_id=producto.pk, activo=True)
        .order_by("fecha_alta", "id")
        .first()
    )
    if not conversion:
        return {
            "cantidad": None,
            "texto": "Sin métrica",
            "help": "El producto no tiene métricas activas registradas.",
        }

    cantidad_origen = _to_decimal(conversion.cantidad_origen, default="1")
    factor = _to_decimal(conversion.factor_conversion, default="0")
    if cantidad_origen <= 0 or factor <= 0:
        return {
            "cantidad": None,
            "texto": "Métrica inválida",
            "help": "La primera métrica activa no tiene una equivalencia válida.",
        }

    factor_unitario = factor / cantidad_origen
    convertido = cantidad / factor_unitario
    unidad = conversion.unidad_origen or conversion.nombre or "presentación"
    return {
        "cantidad": convertido,
        "texto": f"{_decimal_texto(convertido)} {unidad}",
        "help": f"{_decimal_texto(cantidad)} {metrica_base} / {_decimal_texto(factor_unitario)} {metrica_base} por {unidad}.",
    }


def conversion_campos_ajuste_reciente(producto, cantidad):
    conversion = conversion_ajuste_reciente(producto, cantidad)
    return {
        "conversion_texto": conversion.get("texto") or "—",
        "conversion_help": conversion.get("help") or "",
    }


def ajustes_recientes(limit=10):
    entradas = [
        {
            "tipo": "entrada",
            "id": e.id,
            "folio": e.folio,
            "fecha": e.fecha,
            "creado_en": e.creado_en,
            "tipo_display": e.get_tipo_display(),
            "almacen": e.almacen,
            "producto": d.producto if d else None,
            "cantidad": d.cantidad if d else Decimal("0"),
            **conversion_campos_ajuste_reciente(d.producto if d else None, d.cantidad if d else Decimal("0")),
            "reversado": ReversaInventarioService.ajuste_esta_reversado("entrada", e.id),
        }
        for e in EntradaInventario.objects.filter(tipo=EntradaInventario.TIPO_AJUSTE_POSITIVO)
        .exclude(observaciones__icontains="REVERSA_DE=")
        .select_related("almacen")
        .prefetch_related("detalles__producto")
        .order_by("-creado_en")[:limit]
        for d in [e.detalles.first()]
    ]

    salidas = [
        {
            "tipo": "salida",
            "id": s.id,
            "folio": s.folio,
            "fecha": s.fecha,
            "creado_en": s.creado_en,
            "tipo_display": s.get_tipo_display(),
            "almacen": s.almacen,
            "producto": d.producto if d else None,
            "cantidad": d.cantidad if d else Decimal("0"),
            **conversion_campos_ajuste_reciente(d.producto if d else None, d.cantidad if d else Decimal("0")),
            "reversado": ReversaInventarioService.ajuste_esta_reversado("salida", s.id),
        }
        for s in SalidaInventario.objects.filter(tipo=SalidaInventario.TIPO_AJUSTE_NEGATIVO)
        .exclude(observaciones__icontains="REVERSA_DE=")
        .select_related("almacen")
        .prefetch_related("detalles__producto")
        .order_by("-creado_en")[:limit]
        for d in [s.detalles.first()]
    ]

    movimientos = entradas + salidas
    movimientos.sort(key=lambda x: x["creado_en"], reverse=True)
    return movimientos[:limit]
