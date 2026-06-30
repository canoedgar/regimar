from typing import Protocol


class StockVentaPort(Protocol):
    def aplicar_salidas(self, *, almacen_id: int, requeridos: dict) -> None:
        ...


class PrecioClienteVentaPort(Protocol):
    def registrar_ultimo_precio(self, *, cliente, producto, precio, usuario=None, observaciones="") -> None:
        ...


class PagoVentaPort(Protocol):
    def sincronizar_terminal(self, salida, *, usuario=None):
        ...

