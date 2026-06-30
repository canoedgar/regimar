from .bitacora import registrar_bitacora_precio_inventario
from .costos import aplicar_entrada_con_costo, recalcular_costo_promedio_producto
from .stock import aplicar_movimiento_stock


class AfectacionInventarioService:
    """Operaciones de bajo nivel para afectar stock, costos y bitácora."""

    def __init__(self, *, usuario=None):
        self.usuario = usuario if getattr(usuario, "is_authenticated", False) else None

    def entrada_con_costo(self, *, producto_id, almacen_id, cantidad, costo_unitario, producto=None, motivo=""):
        aplicar_entrada_con_costo(
            producto_id=producto_id,
            almacen_id=almacen_id,
            cantidad=cantidad,
            costo_unitario=costo_unitario,
        )
        registrar_bitacora_precio_inventario(
            producto=producto,
            producto_id=producto_id,
            usuario=self.usuario,
            motivo=motivo,
        )

    def salida_con_recalculo(self, *, producto_id, almacen_id, cantidad, producto=None, motivo=""):
        aplicar_movimiento_stock(
            producto_id=producto_id,
            almacen_id=almacen_id,
            delta=-cantidad,
        )
        recalcular_costo_promedio_producto(producto_id)
        registrar_bitacora_precio_inventario(
            producto=producto,
            producto_id=producto_id,
            usuario=self.usuario,
            motivo=motivo,
        )
