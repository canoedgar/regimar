from decimal import Decimal

from inventarios.models import SalidaInventarioDetalleAlmacen
from ventas.models import NotaVenta
from ventas.adapters.catalogos import CatalogosPrecioClienteAdapter
from ventas.adapters.inventario import InventarioStockVentaAdapter
from ventas.adapters.pagos import PagoTerminalVentaAdapter
from ventas.services.inventario_virtual import EntradaVirtualVentaService


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
        stock_port=None,
        precio_cliente_port=None,
        pago_port=None,
    ):
        self.data = data
        self.detalles_validos = detalles_validos
        self.detalles_meta = detalles_meta or []
        self.lineas_stock = lineas_stock or []
        self.almacenes_permitidos = almacenes_permitidos or {}
        self.credito_service = credito_service
        self.stock_port = stock_port or InventarioStockVentaAdapter()
        self.precio_cliente_port = precio_cliente_port or CatalogosPrecioClienteAdapter()
        self.pago_port = pago_port or PagoTerminalVentaAdapter()

    def execute(self):
        requeridos_por_almacen = self._agrupar_requeridos_por_almacen()

        salida = self.data.salida
        salida.almacen = self.lineas_stock[0]["almacen"]
        salida.registrado_por = self.data.contexto.usuario

        self._agregar_observacion_almacenes(salida)
        salida.save()
        nota = self._crear_nota_comercial(salida)
        self.credito_service.marcar_usada(nota)

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
        self._registrar_ultimos_precios(nota, detalles_por_index)

        self.pago_port.sincronizar_terminal(
            nota,
            usuario=self.data.contexto.usuario,
        )

        return nota

    def _crear_nota_comercial(self, salida):
        return NotaVenta.objects.create(
            salida=salida,
            folio=salida.folio,
            fecha=salida.fecha,
            cliente=salida.cliente,
            cliente_ref=salida.cliente_ref,
            forma_pago_venta=salida.forma_pago_venta,
            estado_pago=salida.estado_pago,
            comision_terminal_porcentaje=salida.comision_terminal_porcentaje,
            comision_terminal_monto=salida.comision_terminal_monto,
            cliente_direccion=salida.cliente_direccion,
            cliente_contacto=salida.cliente_contacto,
            logo_nota=salida.logo_nota,
            documento_referencia=salida.documento_referencia,
            motivo=salida.motivo,
            observaciones=salida.observaciones,
            estado=salida.estado,
            cancelada_en=salida.cancelada_en,
            motivo_cancelacion=salida.motivo_cancelacion,
            editada_en=salida.editada_en,
            editada_por=salida.editada_por,
        )

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
            self.stock_port.aplicar_salidas(
                almacen_id=almacen_id,
                requeridos=requeridos,
            )

    def _registrar_ultimos_precios(self, salida, detalles_por_index):
        cliente = getattr(salida, "cliente_ref", None)
        for detalle in detalles_por_index.values():
            self.precio_cliente_port.registrar_ultimo_precio(
                cliente=cliente,
                producto=detalle.producto,
                precio=detalle.precio_unitario,
                usuario=self.data.contexto.usuario,
                observaciones=f"Venta {salida.folio}",
            )
