"""Compatibilidad temporal. La creación de ventas vive en ventas.services.creacion."""

from ventas.services.creacion import VentaService
from ventas.services.inventario_virtual import es_almacen_venta_virtual

__all__ = ["VentaService", "es_almacen_venta_virtual"]
