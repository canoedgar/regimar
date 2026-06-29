from decimal import Decimal

from inventarios.models import EntradaInventario, EntradaInventarioDetalle
from inventarios.services.bitacora import registrar_bitacora_precio_inventario
from inventarios.services.costos import aplicar_entrada_con_costo, costo_virtual_producto
from inventarios.services.folios import next_folio_movimiento


def es_almacen_venta_virtual(almacen) -> bool:
    """
    Identifica almacenes usados para venta sin existencia física previa.
    En estos almacenes la nota genera una entrada automática y después
    la salida normal, dejando trazabilidad entrada/salida sin bloquear por stock 0.
    """
    if not almacen:
        return False
    return bool(
        getattr(almacen, "es_virtual_sistema", False)
        or getattr(almacen, "tipo", "") == "VIRTUAL"
    )


class EntradaVirtualVentaService:
    """
    Registra entradas automáticas para ventas desde almacenes virtuales.

    Este servicio solo atiende la trazabilidad de entrada virtual y la suma de
    stock previa a la salida. El descuento de salida sigue viviendo en el flujo
    de venta que llama a inventarios.services.stock.aplicar_movimientos_salida.
    """

    def __init__(self, *, detalles_validos, almacenes_permitidos, usuario=None):
        self.detalles_validos = detalles_validos or []
        self.almacenes_permitidos = almacenes_permitidos or {}
        self.usuario = usuario

    def registrar(self, *, salida, requeridos_por_almacen):
        entradas = []
        productos_por_id = {
            detalle.producto_id: detalle.producto
            for detalle in self.detalles_validos
            if getattr(detalle, "producto_id", None)
        }

        for almacen_id, agregados in (requeridos_por_almacen or {}).items():
            almacen = self.almacenes_permitidos.get(str(almacen_id))
            if not es_almacen_venta_virtual(almacen):
                continue

            entrada = self._crear_entrada(salida=salida, almacen=almacen)
            entradas.append(entrada)
            self._crear_detalles_y_aplicar_stock(
                entrada=entrada,
                salida=salida,
                almacen=almacen,
                almacen_id=almacen_id,
                agregados=agregados,
                productos_por_id=productos_por_id,
            )

        return entradas

    def _crear_entrada(self, *, salida, almacen):
        return EntradaInventario.objects.create(
            folio=next_folio_movimiento(
                tipo=EntradaInventario.TIPO_AJUSTE_POSITIVO,
                width=6,
                prefix="EV",
            ),
            fecha=salida.fecha,
            tipo=EntradaInventario.TIPO_AJUSTE_POSITIVO,
            almacen=almacen,
            documento_referencia=salida.folio,
            motivo="Entrada automática por venta sin inventario",
            registrado_por=self.usuario,
            tiene_xml=False,
            xml_contenido="",
            observaciones=(
                f"Entrada automática generada por la nota de venta {salida.folio}.\n"
                "Flujo: venta desde almacén virtual; se registra entrada y salida en la misma transacción."
            ),
        )

    def _crear_detalles_y_aplicar_stock(
        self,
        *,
        entrada,
        salida,
        almacen,
        almacen_id,
        agregados,
        productos_por_id,
    ):
        for producto_id, cantidad in (agregados or {}).items():
            producto = productos_por_id.get(producto_id)
            costo_unitario = costo_virtual_producto(producto)

            EntradaInventarioDetalle.objects.create(
                entrada=entrada,
                producto_id=producto_id,
                almacen=almacen,
                cantidad=cantidad,
                costo_unitario=costo_unitario,
                costo_total=cantidad * costo_unitario,
                presentacion_nombre="Kilos",
                presentacion_conversion_id="default",
                cantidad_presentacion=cantidad,
                presentacion_factor_conversion=Decimal("1"),
                presentacion_metrica_default=getattr(producto, "metrica", "kg") if producto else "kg",
                presentacion_equivalencia_texto="Entrada automática por venta virtual",
            )

            aplicar_entrada_con_costo(
                producto_id=producto_id,
                almacen_id=almacen_id,
                cantidad=cantidad,
                costo_unitario=costo_unitario,
            )
            registrar_bitacora_precio_inventario(
                producto_id=producto_id,
                usuario=self.usuario,
                motivo=f"Entrada automática por venta virtual {salida.folio}",
            )
