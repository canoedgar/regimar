from inventarios.services.stock import aplicar_movimientos_salida


class InventarioStockVentaAdapter:
    def aplicar_salidas(self, *, almacen_id: int, requeridos: dict) -> None:
        aplicar_movimientos_salida(
            almacen_id=almacen_id,
            requeridos=requeridos,
        )

