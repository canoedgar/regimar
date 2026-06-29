from decimal import Decimal

from catalogos.services.clientes_precios import registrar_ultimo_precio_cliente
from inventarios.models import SalidaInventarioDetalleAlmacen
from inventarios.services.stock import aplicar_movimientos_salida
from ventas.services.inventario_virtual import EntradaVirtualVentaService
from ventas.services.pagos import sincronizar_comision_y_pago_terminal


class CrearNotaVentaUseCase:
    """Orquesta la persistencia completa de una nota de venta."""

    def __init__(
        self,
        *,
        data,
        detalles_validos,
        detalles_meta,
        lineas_stock,
        almacenes_permitidos,
        credito_service,
    ):
        self.data = data
        self.detalles_validos = detalles_validos
        self.detalles_meta = detalles_meta or []
        self.lineas_stock = lineas_stock or []
        self.almacenes_permitidos = almacenes_permitidos or {}
        self.credito_service = credito_service

    def execute(self):
        requeridos_por_almacen = self._agrupar_requeridos_por_almacen()

        salida = self.data.salida
        salida.almacen = self.lineas_stock[0]["almacen"]
        salida.registrado_por = self.data.contexto.usuario

        self._agregar_observacion_almacenes(salida)
        salida.save()
        self.credito_service.marcar_usada(salida)

        EntradaVirtualVentaService(
            detalles_validos=self.detalles_validos,
            almacenes_permitidos=self.almacenes_permitidos,
            usuario=self.data.contexto.usuario,
        ).registrar(
            salida=salida,
            requeridos_por_almacen=requeridos_por_almacen,
        )

        detalles_por_index = self._guardar_detalles(salida)
        self._guardar_asignaciones(detalles_por_index)
        self._aplicar_salidas_inventario(requeridos_por_almacen)
        self._registrar_ultimos_precios(salida, detalles_por_index)

        sincronizar_comision_y_pago_terminal(
            salida,
            usuario=self.data.contexto.usuario,
        )

        return salida

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

    def _agregar_observacion_almacenes(self, salida):
        almacenes_usados = []
        vistos = set()

        for linea in self.lineas_stock:
            almacen = linea["almacen"]
            key = str(almacen.id)

            if key not in vistos:
                vistos.add(key)
                almacenes_usados.append(str(almacen))

        if len(almacenes_usados) <= 1:
            return

        nota_almacenes = "Almacenes surtidos: " + ", ".join(almacenes_usados)
        observaciones = (salida.observaciones or "").strip()

        salida.observaciones = (
            observaciones + "\n" + nota_almacenes
            if observaciones
            else nota_almacenes
        )

    def _guardar_detalles(self, salida):
        detalles_por_index = {}

        for index, detalle in enumerate(self.detalles_validos):
            meta = self.detalles_meta[index] if index < len(self.detalles_meta) else {}

            detalle.salida = salida
            detalle.almacen = salida.almacen

            producto = getattr(detalle, "producto", None)
            detalle.costo_unitario_aplicado = (
                getattr(producto, "costo_promedio", Decimal("0"))
                if producto else Decimal("0")
            )

            detalle.presentacion_nombre = (
                meta.get("presentacion_nombre")
                or getattr(detalle, "presentacion_nombre", "")
                or "Kilos"
            )
            detalle.presentacion_conversion_id = (
                meta.get("presentacion_id")
                or "default"
            )
            cantidad_presentacion = meta.get("cantidad_presentacion")
            detalle.cantidad_presentacion = (
                cantidad_presentacion
                if cantidad_presentacion is not None
                else detalle.cantidad
            )
            detalle.presentacion_factor_conversion = (
                meta.get("factor_conversion")
                or Decimal("1")
            )
            detalle.presentacion_metrica_default = (
                meta.get("metrica_default")
                or "kg"
            )
            detalle.presentacion_equivalencia_texto = (
                meta.get("equivalencia_texto")
                or f"1 {detalle.presentacion_nombre} = "
                   f"{detalle.presentacion_factor_conversion} "
                   f"{detalle.presentacion_metrica_default}"
            )

            detalle.save()
            detalles_por_index[index] = detalle

        return detalles_por_index

    def _guardar_asignaciones(self, detalles_por_index):
        for linea in self.lineas_stock:
            detalle = detalles_por_index.get(linea.get("item_index"))

            if not detalle:
                continue

            SalidaInventarioDetalleAlmacen.objects.create(
                detalle=detalle,
                almacen=linea["almacen"],
                cantidad=linea["cantidad"],
            )

    def _aplicar_salidas_inventario(self, requeridos_por_almacen):
        for almacen_id, requeridos in requeridos_por_almacen.items():
            aplicar_movimientos_salida(
                almacen_id=almacen_id,
                requeridos=requeridos,
            )

    def _registrar_ultimos_precios(self, salida, detalles_por_index):
        cliente = getattr(salida, "cliente_ref", None)
        for detalle in detalles_por_index.values():
            registrar_ultimo_precio_cliente(
                cliente=cliente,
                producto=detalle.producto,
                precio=detalle.precio_unitario,
                usuario=self.data.contexto.usuario,
                observaciones=f"Venta {salida.folio}",
            )
