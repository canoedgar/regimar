# inventarios/services/bitacora.py

from catalogos.models import Producto


def registrar_bitacora_precio_inventario(*, producto=None, producto_id=None, usuario=None, motivo=""):
    """
    Registra bitácora comercial del producto después de un movimiento de inventario.

    La bitácora no debe impedir guardar inventario, por eso este servicio absorbe
    errores externos del catálogo/precios.
    """
    try:
        if producto is None:
            producto = Producto.objects.get(pk=producto_id)
        else:
            producto.refresh_from_db()

        from catalogos.services.precios import registrar_bitacora_precio_producto

        registrar_bitacora_precio_producto(
            producto,
            usuario=usuario,
            motivo=motivo,
        )
    except Exception:
        pass
