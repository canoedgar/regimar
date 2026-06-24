"""Consultas de precios comerciales por cliente para UI/API."""

from catalogos.models import ClienteProductoPrecio, ParametroSistema


def get_precios_cliente_payload(*, cliente_id, producto_ids=None):
    producto_ids = producto_ids or []
    vigencia_dias = ParametroSistema.get_int("PRECIO_VIGENCIA_DIAS", 0)
    if not cliente_id:
        return {"precios": {}, "vigencia_dias": vigencia_dias}

    precios = ClienteProductoPrecio.objects.filter(cliente_id=cliente_id)
    ids_validos = [pid for pid in producto_ids if str(pid).isdigit()]
    if ids_validos:
        precios = precios.filter(producto_id__in=ids_validos)

    data = {}
    for precio in precios.select_related("producto"):
        data[str(precio.producto_id)] = {
            "precio": float(precio.ultimo_precio or 0),
            "fecha": precio.fecha_ultimo_precio.isoformat() if precio.fecha_ultimo_precio else "",
            "dias_sin_compra": precio.dias_sin_compra,
            "vigente": precio.vigente,
        }

    return {"precios": data, "vigencia_dias": vigencia_dias}
