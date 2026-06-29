from decimal import Decimal

from catalogos.models import Producto
from inventarios.services.stock import errores_stock_humano, validar_stock_suficiente
from ventas.services.inventario_virtual import es_almacen_venta_virtual


class ValidarNotaVentaService:
    """Valida precio, crédito y disponibilidad de stock para una nota de venta."""

    def __init__(
        self,
        *,
        detalles_validos,
        lineas_stock,
        almacenes_permitidos,
        credito_service,
        precio_service,
    ):
        self.detalles_validos = detalles_validos or []
        self.lineas_stock = lineas_stock or []
        self.almacenes_permitidos = almacenes_permitidos or {}
        self.credito_service = credito_service
        self.precio_service = precio_service

    def validar(self):
        requeridos_por_almacen = self._agrupar_requeridos_por_almacen()

        productos = list(Producto.objects.filter(
            id__in=[detalle.producto_id for detalle in self.detalles_validos]
        ))
        productos_por_id = {producto.id: str(producto) for producto in productos}
        productos_obj_por_id = {producto.id: producto for producto in productos}

        errores = []
        errores.extend(self._validar_precios_minimos(productos_obj_por_id))
        errores.extend(self._validar_credito_cliente())
        errores.extend(self._validar_stock_fisico(requeridos_por_almacen, productos_por_id))
        return errores

    def _validar_credito_cliente(self):
        return self.credito_service.validar(self.detalles_validos)

    def _validar_precios_minimos(self, productos_obj_por_id):
        return self.precio_service.validar_detalles(
            detalles_validos=self.detalles_validos,
            productos_por_id=productos_obj_por_id,
        )

    def _validar_stock_fisico(self, requeridos_por_almacen, productos_por_id):
        errores = []

        for almacen_id, requeridos in requeridos_por_almacen.items():
            almacen = self.almacenes_permitidos.get(str(almacen_id))

            # Los almacenes virtuales representan ventas sin existencia física previa.
            # No deben bloquearse por stock 0 porque el flujo genera entrada automática
            # y salida de venta en la misma transacción.
            if es_almacen_venta_virtual(almacen):
                continue

            ok, disponibles, faltantes = validar_stock_suficiente(
                almacen_id=almacen_id,
                requeridos=requeridos,
            )

            if not ok:
                errores.extend(
                    errores_stock_humano(
                        almacen_nombre=str(almacen),
                        faltantes=faltantes,
                        disponibles=disponibles,
                        productos_por_id=productos_por_id,
                    )
                )

        return errores

    def _agrupar_requeridos_por_almacen(self):
        requeridos = {}

        for linea in self.lineas_stock:
            almacen_id = linea["almacen"].id
            producto_id = linea["producto"].id

            requeridos.setdefault(almacen_id, {})
            requeridos[almacen_id][producto_id] = (
                requeridos[almacen_id].get(producto_id, Decimal("0"))
                + linea["cantidad"]
            )

        return requeridos
