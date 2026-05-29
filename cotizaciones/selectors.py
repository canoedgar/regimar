from decimal import Decimal

from django.db.models import Prefetch

from catalogos.models import Cliente, Producto
from .models import CotizacionPrecio, CotizacionPrecioDetalle


def clientes_para_cotizacion():
    return Cliente.objects.all().order_by("nombre_fiscal")


def cotizaciones_listado():
    return (
        CotizacionPrecio.objects
        .select_related("cliente", "creado_por", "autorizado_por")
        .prefetch_related("detalles")
        .order_by("-fecha", "-id")
    )


def get_cotizacion_detalle(pk):
    return (
        CotizacionPrecio.objects
        .select_related("cliente", "creado_por", "autorizado_por")
        .prefetch_related(
            Prefetch(
                "detalles",
                queryset=CotizacionPrecioDetalle.objects.select_related("producto").order_by("producto__nombre"),
            )
        )
        .get(pk=pk)
    )


def _decimal_to_float(value):
    return float(value or Decimal("0"))


def productos_para_cotizacion_ui():
    productos = Producto.objects.all().order_by("nombre")
    data = []
    for producto in productos:
        costo = producto.costo_promedio or producto.ultimo_costo_compra or Decimal("0")
        data.append({
            "id": producto.id,
            "nombre": producto.nombre,
            "metrica": producto.metrica or "KG",
            "costo_base": _decimal_to_float(costo),
            "precio_sugerido": _decimal_to_float(producto.precio),
            "precio_minimo": _decimal_to_float(producto.precio_minimo),
            "maneja_peso_variable": bool(getattr(producto, "maneja_peso_variable", False)),
        })
    return data
