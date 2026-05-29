from decimal import Decimal, InvalidOperation

from catalogos.models import Almacen, Cliente, ClienteProductoPrecio
from inventarios.models import InventarioStock
from inventarios.utils import get_almacen_default


def _to_decimal(value, default=None):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _decimal_text(value):
    dec = _to_decimal(value, default=Decimal("0"))
    txt = format(dec, "f")

    if "." in txt:
        txt = txt.rstrip("0").rstrip(".")

    return txt or "0"


def _nombre_metrica(obj):
    if obj is None:
        return ""

    return (
        getattr(obj, "abreviatura", None)
        or getattr(obj, "nombre", None)
        or getattr(obj, "nombre_metrica", None)
        or str(obj)
    )


def _conversiones_producto(producto):
    default_name = _nombre_metrica(getattr(producto, "metrica", None)) or "kg"

    conversiones = [{
        "id": "default",
        "cantidad_origen": 1.0,
        "unidad_origen": default_name,
        "factor_conversion": 1.0,
        "equivalencia_texto": f"1 {default_name} = 1 {default_name}",
        "es_default": True,
    }]

    rel = None

    for attr in ("conversiones_metricas", "conversiones"):
        if hasattr(producto, attr):
            rel = getattr(producto, attr)
            break

    if rel is None:
        return conversiones

    try:
        rows = rel.all()
    except Exception:
        return conversiones

    for conv in rows:
        cantidad_origen = (
            _to_decimal(
                getattr(conv, "cantidad_origen", None),
                default=Decimal("1"),
            )
            or Decimal("1")
        )

        factor = (
            _to_decimal(
                getattr(conv, "factor_conversion", None),
                default=Decimal("0"),
            )
            or Decimal("0")
        )

        unidad_origen = (
            _nombre_metrica(getattr(conv, "unidad_origen", None))
            or _nombre_metrica(getattr(conv, "metrica", None))
            or default_name
        )

        conversiones.append({
            "id": str(getattr(conv, "id", "")) or f"conv-{len(conversiones)}",
            "cantidad_origen": float(cantidad_origen),
            "unidad_origen": unidad_origen,
            "factor_conversion": float(factor),
            "equivalencia_texto": (
                getattr(conv, "equivalencia_texto", None)
                or f"{_decimal_text(cantidad_origen)} "
                   f"{unidad_origen} = "
                   f"{_decimal_text(factor)} "
                   f"{default_name}"
            ),
            "es_default": False,
        })

    return conversiones


def build_productos_ui():
    stocks = (
        InventarioStock.objects
        .filter(almacen__es_activo=True)
        .select_related("producto", "almacen")
        .order_by("producto__nombre", "almacen__tipo", "almacen__nombre")
    )

    productos_map = {}

    for stock in stocks:
        producto = stock.producto
        producto_id = str(producto.id)

        item = productos_map.setdefault(producto_id, {
            "id": producto_id,
            "nombre": producto.nombre,
            "stock": 0.0,
            "precio": float(getattr(producto, "precio", 0) or 0),
            "precio_minimo": float(getattr(producto, "precio_minimo", 0) or 0),
            "maneja_peso_variable": bool(getattr(producto, "maneja_peso_variable", False)),
            "costo_promedio": float(getattr(producto, "costo_promedio", 0) or 0),
            "ultimo_costo_compra": float(getattr(producto, "ultimo_costo_compra", 0) or 0),
            "codigo": getattr(producto, "codigo", "") or "",
            "clave_busqueda": getattr(producto, "clave_busqueda", "") or "",
            "metrica_default": _nombre_metrica(
                getattr(producto, "metrica", None)
            ) or "kg",
            "conversiones": _conversiones_producto(producto),
            "almacenes": [],
        })

        cantidad = float(stock.cantidad or 0)
        item["stock"] += cantidad

        item["almacenes"].append({
            "id": str(stock.almacen_id),
            "codigo": getattr(stock.almacen, "codigo", "") or "",
            "nombre": getattr(stock.almacen, "nombre", "") or "",
            "tipo": getattr(stock.almacen, "tipo", "") or "",
            "stock": cantidad,
            "label": (
                f"{getattr(stock.almacen, 'codigo', '')} - "
                f"{getattr(stock.almacen, 'nombre', '')}"
            ).strip(" -"),
        })

    cliente_precios = ClienteProductoPrecio.objects.select_related("cliente", "producto")

    for precio_cliente in cliente_precios:
        producto_id = str(precio_cliente.producto_id)
        if producto_id not in productos_map:
            continue
        item = productos_map[producto_id]
        item.setdefault("precios_clientes", {})[str(precio_cliente.cliente_id)] = {
            "precio": float(precio_cliente.ultimo_precio or 0),
            "fecha": precio_cliente.fecha_ultimo_precio.isoformat() if precio_cliente.fecha_ultimo_precio else "",
            "dias_sin_compra": precio_cliente.dias_sin_compra,
            "vigente": precio_cliente.vigente,
        }

    productos_ui = list(productos_map.values())
    productos_ui.sort(key=lambda item: (item.get("nombre") or "").lower())

    return productos_ui


def get_contexto_salida_venta():
    almacenes_qs = Almacen.objects.filter(
        es_activo=True
    ).order_by(
        "tipo",
        "nombre",
    )

    almacen_default = get_almacen_default() or almacenes_qs.first()

    clientes = Cliente.objects.all().order_by("nombre_fiscal")

    return {
        "productos_ui": build_productos_ui(),
        "clientes": clientes,
        "almacenes_qs": almacenes_qs,
        "almacen_default": almacen_default,
    }