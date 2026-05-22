from decimal import Decimal
from django.utils import timezone
from catalogos.models import ClienteProductoPrecio, ParametroSistema


def registrar_ultimo_precio_cliente(*, cliente, producto, precio, usuario=None, observaciones="Venta"):
    if not cliente or not producto:
        return None
    precio = Decimal(str(precio or 0)).quantize(Decimal("0.01"))
    obj, created = ClienteProductoPrecio.objects.get_or_create(
        cliente=cliente,
        producto=producto,
        defaults={
            "ultimo_precio": precio,
            "precio_anterior": Decimal("0.00"),
            "actualizado_por": usuario if getattr(usuario, "is_authenticated", False) else None,
            "observaciones": observaciones,
        },
    )
    if not created:
        obj.precio_anterior = obj.ultimo_precio
        obj.ultimo_precio = precio
        obj.fecha_ultimo_precio = timezone.now()
        obj.actualizado_por = usuario if getattr(usuario, "is_authenticated", False) else None
        obj.observaciones = observaciones
        obj.save(update_fields=["precio_anterior", "ultimo_precio", "fecha_ultimo_precio", "actualizado_por", "observaciones"])
    return obj


def obtener_precio_cliente(cliente_id, producto_id):
    if not cliente_id or not producto_id:
        return None
    return ClienteProductoPrecio.objects.filter(cliente_id=cliente_id, producto_id=producto_id).first()


def dias_vigencia_precio():
    return ParametroSistema.get_int("PRECIO_VIGENCIA_DIAS", 0)
