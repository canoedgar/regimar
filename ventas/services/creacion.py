from decimal import Decimal

from catalogos.models import Producto
from catalogos.services.clientes_precios import registrar_ultimo_precio_cliente
from inventarios.models import EntradaInventario, EntradaInventarioDetalle, SalidaInventarioDetalleAlmacen
from inventarios.services.bitacora import registrar_bitacora_precio_inventario
from inventarios.services.costos import aplicar_entrada_con_costo, costo_virtual_producto
from inventarios.services.stock import (
    aplicar_movimientos_salida,
    errores_stock_humano,
    validar_stock_suficiente,
)
from inventarios.services.folios import next_folio_movimiento
from ventas.services.venta_credito import VentaCreditoService
from ventas.services.venta_data import VentaOperacionData, VentaRequestContext
from ventas.services.venta_precio import VentaPrecioMinimoService
from ventas.services.comisiones import aplicar_comision_terminal, es_nota_terminal


def es_almacen_venta_virtual(almacen) -> bool:
    """
    Identifica almacenes usados para venta sin existencia física previa.
    En estos almacenes la nota debe generar una entrada automática y después
    la salida normal, dejando trazabilidad entrada/salida sin bloquear por stock 0.
    """
    if not almacen:
        return False
    return bool(
        getattr(almacen, "es_virtual_sistema", False)
        or getattr(almacen, "tipo", "") == "VIRTUAL"
    )



class VentaService:
    def __init__(
        self,
        *,
        detalles_validos,
        detalles_meta,
        lineas_stock,
        almacenes_permitidos,
        data=None,
        form=None,
        request=None,
        request_context=None,
        venta_existente=None,
        total_venta_override=None,
        validar_credito=None,
    ):
        # Compatibilidad temporal: si alguna vista antigua aún envía form/request,
        # los adaptamos aquí. Los flujos nuevos deben enviar `data`.
        if data is None:
            if form is None:
                raise ValueError("VentaService requiere data o form.")
            data = VentaOperacionData.from_form(
                form,
                request_context=request_context or VentaRequestContext.from_request(request),
                venta_existente=venta_existente,
                total_venta_override=total_venta_override,
                validar_credito=True if validar_credito is None else validar_credito,
            )
        else:
            if request_context is not None:
                data.contexto = request_context
            if venta_existente is not None:
                data.venta_existente = venta_existente
            if total_venta_override is not None:
                data.total_venta_override = total_venta_override
            if validar_credito is not None:
                data.validar_credito = validar_credito

        self.data = data
        self.detalles_validos = detalles_validos
        self.detalles_meta = detalles_meta
        self.lineas_stock = lineas_stock
        self.almacenes_permitidos = almacenes_permitidos
        self.credito_service = VentaCreditoService(
            cliente=self.data.cliente or getattr(self.data.salida, "cliente_ref", None),
            fecha_venta=self.data.fecha or getattr(self.data.salida, "fecha", None),
            contexto=self.data.contexto,
            venta_existente=self.data.venta_existente,
            total_venta_override=self.data.total_venta_override,
            validar_credito=self.data.validar_credito,
        )
        self.precio_service = VentaPrecioMinimoService(
            cliente=self.data.cliente or getattr(self.data.salida, "cliente_ref", None),
            contexto=self.data.contexto,
        )

    def validar_stock(self):
        requeridos_por_almacen = self._agrupar_requeridos_por_almacen()

        productos = list(Producto.objects.filter(
            id__in=[detalle.producto_id for detalle in self.detalles_validos]
        ))
        productos_por_id = {producto.id: str(producto) for producto in productos}
        productos_obj_por_id = {producto.id: producto for producto in productos}

        errores = []

        errores.extend(self._validar_precios_minimos(productos_obj_por_id))
        errores.extend(self._validar_credito_cliente())

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

    def guardar(self):
        requeridos_por_almacen = self._agrupar_requeridos_por_almacen()

        salida = self.data.salida
        salida.almacen = self.lineas_stock[0]["almacen"]
        salida.registrado_por = self.data.contexto.usuario

        self._agregar_observacion_almacenes(salida)
        salida.save()
        self.credito_service.marcar_usada(salida)

        self._registrar_entradas_virtuales(salida, requeridos_por_almacen)

        detalles_por_index = self._guardar_detalles(salida)
        self._guardar_asignaciones(detalles_por_index)

        for almacen_id, requeridos in requeridos_por_almacen.items():
            aplicar_movimientos_salida(
                almacen_id=almacen_id,
                requeridos=requeridos,
            )

        cliente = getattr(salida, "cliente_ref", None)
        for detalle in detalles_por_index.values():
            registrar_ultimo_precio_cliente(
                cliente=cliente,
                producto=detalle.producto,
                precio=detalle.precio_unitario,
                usuario=self.data.contexto.usuario,
                observaciones=f"Venta {salida.folio}",
            )

        aplicar_comision_terminal(salida)
        self._sincronizar_pago_terminal(salida)

        return salida

    def _sincronizar_pago_terminal(self, salida):
        if not es_nota_terminal(salida):
            return None

        from cartera.models import PagoMetodoDetalle
        from cartera.services.cartera import sincronizar_pago_automatico_nota_pagada

        return sincronizar_pago_automatico_nota_pagada(
            salida,
            usuario=self.data.contexto.usuario,
            metodo=PagoMetodoDetalle.METODO_TARJETA,
            fecha_pago=salida.fecha,
        )

    def _registrar_entradas_virtuales(self, salida, requeridos_por_almacen):
        """
        Para almacenes virtuales genera una entrada automática por venta.
        Luego el flujo existente registra la salida de inventario de la nota.
        Resultado: trazabilidad completa entrada/salida y stock neto sin negativos.
        """
        productos_por_id = {
            detalle.producto_id: detalle.producto
            for detalle in self.detalles_validos
            if getattr(detalle, "producto_id", None)
        }

        for almacen_id, agregados in (requeridos_por_almacen or {}).items():
            almacen = self.almacenes_permitidos.get(str(almacen_id))
            if not es_almacen_venta_virtual(almacen):
                continue

            entrada = EntradaInventario.objects.create(
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
                registrado_por=self.data.contexto.usuario,
                tiene_xml=False,
                xml_contenido="",
                observaciones=(
                    f"Entrada automática generada por la nota de venta {salida.folio}.\n"
                    "Flujo: venta desde almacén virtual; se registra entrada y salida en la misma transacción."
                ),
            )

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

                usuario = self.data.contexto.usuario
                aplicar_entrada_con_costo(
                    producto_id=producto_id,
                    almacen_id=almacen_id,
                    cantidad=cantidad,
                    costo_unitario=costo_unitario,
                )
                registrar_bitacora_precio_inventario(
                    producto_id=producto_id,
                    usuario=usuario,
                    motivo=f"Entrada automática por venta virtual {salida.folio}",
                )

    def _validar_credito_cliente(self):
        return self.credito_service.validar(self.detalles_validos)

    def _validar_precios_minimos(self, productos_obj_por_id):
        return self.precio_service.validar_detalles(
            detalles_validos=self.detalles_validos,
            productos_por_id=productos_obj_por_id,
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