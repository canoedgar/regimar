from decimal import Decimal

from catalogos.models import Producto
from catalogos.services.clientes_precios import registrar_ultimo_precio_cliente
from catalogos.services.credito_clientes import money, total_detalles_venta
from inventarios.models import SalidaInventarioDetalle, SalidaInventarioDetalleAlmacen
from inventarios.services.stock import aplicar_movimientos_salida
from ventas.services.venta_parser import VentaPostParser
from ventas.services.venta_credito import (
    marcar_autorizacion_credito_venta_usada,
    validar_credito_venta,
)
from ventas.services.venta_data import VentaOperacionData, VentaRequestContext
from ventas.services.venta_precio import VentaPrecioMinimoService
from ventas.services.creacion import VentaService
from ventas.services.comisiones import (
    calcular_total_con_comision,
    get_subtotal_nota,
)
from ventas.services.inventario_virtual import EntradaVirtualVentaService
from ventas.services.pagos import sincronizar_comision_y_pago_terminal
from django.utils import timezone


def marcar_nota_editada(salida, user=None):
    salida.editada_en = timezone.now()
    salida.editada_por = user if getattr(user, "is_authenticated", False) else None
    salida.save(update_fields=["editada_en", "editada_por"])



class EditarDatosNotaService:
    def __init__(self, *, form, user=None, request=None):
        self.form = form
        self.user = user
        self.request = request
        self.autorizacion_credito = None

    def validar(self):
        salida_actual = self.form.instance
        cliente = self.form.cleaned_data.get("cliente_ref") if hasattr(self.form, "cleaned_data") else None
        fecha = self.form.cleaned_data.get("fecha") if hasattr(self.form, "cleaned_data") else None
        if not cliente:
            return []

        subtotal = get_subtotal_nota(salida_actual)
        total_venta = calcular_total_con_comision(
            subtotal,
            forma_pago=self.form.cleaned_data.get("forma_pago_venta"),
            porcentaje=getattr(salida_actual, "comision_terminal_porcentaje", None),
        )
        errores, autorizacion = validar_credito_venta(
            cliente=cliente,
            total_venta=total_venta,
            fecha_venta=fecha,
            contexto=VentaRequestContext.from_request(self.request),
            venta_existente=salida_actual,
        )
        self.autorizacion_credito = autorizacion
        return errores

    def execute(self):
        salida = self.form.save(commit=False)
        salida.editada_en = timezone.now()
        salida.editada_por = self.user if getattr(self.user, "is_authenticated", False) else None
        salida.save()
        sincronizar_comision_y_pago_terminal(salida, self.user)
        marcar_autorizacion_credito_venta_usada(self.autorizacion_credito, salida)
        return salida


class AjustarPreciosNotaService:
    def __init__(self, *, formset, salida, user=None, request=None):
        self.formset = formset
        self.salida = salida
        self.user = user
        self.request = request
        self.autorizacion_credito = None

    def validar(self):
        """
        Valida que el ajuste de precios respete el precio mínimo del producto.

        Regla:
        - El importe de la nota se calcula con cantidad KG/base × precio KG/base.
        - El precio capturado no puede quedar por debajo del precio mínimo autorizado.
        - Se permite solo cuando ya existe un precio cliente-producto registrado con ese mismo precio,
          que es la regla que ya usa el flujo actual de venta para reconocer un precio autorizado.
        """
        errores = []
        cliente = getattr(self.salida, "cliente_ref", None)

        for form in self.formset.forms:
            if not hasattr(form, "cleaned_data") or not form.cleaned_data:
                continue

            detalle = form.instance
            producto = getattr(detalle, "producto", None)
            precio = form.cleaned_data.get("precio_unitario")

            if not producto or precio is None:
                continue

            precio_minimo = getattr(producto, "precio_minimo", Decimal("0")) or Decimal("0")
            if precio_minimo <= 0 or precio >= precio_minimo:
                continue

            precio_service = VentaPrecioMinimoService(cliente=cliente)
            if precio_service.precio_ya_autorizado(producto=producto, precio=precio):
                continue

            errores.append(
                f"{producto.nombre}: el precio capturado ${precio} "
                f"es menor al precio mínimo autorizado ${precio_minimo}."
            )

        if not errores:
            errores.extend(self._validar_credito())

        return errores

    def _validar_credito(self):
        cliente = getattr(self.salida, "cliente_ref", None)
        if not cliente:
            return []

        total = Decimal("0.00")
        for form in self.formset.forms:
            if not hasattr(form, "cleaned_data") or not form.cleaned_data:
                continue
            detalle = form.instance
            cantidad = money(getattr(detalle, "cantidad", 0))
            precio = money(form.cleaned_data.get("precio_unitario"))
            total += cantidad * precio

        total_venta = calcular_total_con_comision(
            money(total),
            forma_pago=getattr(self.salida, "forma_pago_venta", ""),
            porcentaje=getattr(self.salida, "comision_terminal_porcentaje", None),
        )
        errores, autorizacion = validar_credito_venta(
            cliente=cliente,
            total_venta=total_venta,
            fecha_venta=getattr(self.salida, "fecha", None),
            contexto=VentaRequestContext.from_request(self.request),
            venta_existente=self.salida,
        )
        self.autorizacion_credito = autorizacion
        return errores

    def execute(self):
        errores = self.validar()
        if errores:
            raise ValueError("; ".join(errores))

        detalles = self.formset.save()
        marcar_nota_editada(self.salida, self.user)
        sincronizar_comision_y_pago_terminal(self.salida, self.user)
        marcar_autorizacion_credito_venta_usada(self.autorizacion_credito, self.salida)
        cliente = getattr(self.salida, "cliente_ref", None)
        for detalle in detalles:
            registrar_ultimo_precio_cliente(
                cliente=cliente,
                producto=detalle.producto,
                precio=detalle.precio_unitario,
                usuario=self.user if getattr(self.user, "is_authenticated", False) else None,
                observaciones=f"Ajuste de precio en nota {self.salida.folio}",
            )
        return detalles


class AgregarProductosNotaService:
    def __init__(
        self,
        *,
        salida,
        formset,
        almacenes_permitidos,
        request=None,
        post_data=None,
        user=None,
        request_context=None,
    ):
        self.request = request
        self.post_data = post_data if post_data is not None else getattr(request, "POST", None)
        self.user = user if user is not None else getattr(request, "user", None)
        self.request_context = request_context or VentaRequestContext.from_request(request)
        self.salida = salida
        self.formset = formset
        self.almacenes_permitidos = almacenes_permitidos
        self.resultado_parseo = None
        self.autorizacion_credito = None

    def validar(self):
        if not self.formset.is_valid():
            return ["Revisa los productos capturados."]

        errores = []
        repetidos = self._productos_repetidos()
        if repetidos:
            errores.append(
                "No se pueden agregar productos que ya existen en la nota o están repetidos en esta edición: "
                + ", ".join(repetidos)
                + "."
            )
            return errores

        parser = VentaPostParser(
            post_data=self.post_data,
            formset=self.formset,
            almacenes_permitidos=self.almacenes_permitidos,
        )
        self.resultado_parseo = parser.parse()
        errores.extend(self.resultado_parseo["errores"])
        if errores:
            return errores

        venta_data = VentaOperacionData(
            salida=self.salida,
            cliente=self.salida.cliente_ref,
            fecha=self.salida.fecha,
            contexto=self.request_context,
            validar_credito=False,
        )
        venta_service = VentaService(
            data=venta_data,
            detalles_validos=self.resultado_parseo["detalles_validos"],
            detalles_meta=self.resultado_parseo["detalles_meta"],
            lineas_stock=self.resultado_parseo["lineas_stock"],
            almacenes_permitidos=self.almacenes_permitidos,
        )
        errores.extend(venta_service.validar_stock())
        if not errores:
            errores.extend(self._validar_credito())
        return errores

    def _validar_credito(self):
        cliente = getattr(self.salida, "cliente_ref", None)
        if not cliente or self.resultado_parseo is None:
            return []
        subtotal_proyectado = money(get_subtotal_nota(self.salida) + total_detalles_venta(self.resultado_parseo["detalles_validos"]))
        total_proyectado = calcular_total_con_comision(
            subtotal_proyectado,
            forma_pago=getattr(self.salida, "forma_pago_venta", ""),
            porcentaje=getattr(self.salida, "comision_terminal_porcentaje", None),
        )
        errores, autorizacion = validar_credito_venta(
            cliente=cliente,
            total_venta=total_proyectado,
            fecha_venta=getattr(self.salida, "fecha", None),
            contexto=self.request_context,
            venta_existente=self.salida,
        )
        self.autorizacion_credito = autorizacion
        return errores

    def execute(self):
        if self.resultado_parseo is None:
            errores = self.validar()
            if errores:
                raise ValueError("; ".join(errores))

        detalles = self._guardar_productos()
        marcar_nota_editada(self.salida, self.user)
        sincronizar_comision_y_pago_terminal(self.salida, self.user)
        marcar_autorizacion_credito_venta_usada(self.autorizacion_credito, self.salida)
        return detalles

    def _productos_repetidos(self):
        productos_existentes = set(self.salida.detalles.values_list("producto_id", flat=True))
        vistos = set()
        repetidos = []
        try:
            total = int(self.post_data.get("nuevos-TOTAL_FORMS", "0") or 0)
        except (TypeError, ValueError):
            total = 0

        for idx in range(total):
            raw_producto_id = (self.post_data.get(f"nuevos-{idx}-producto") or "").strip()
            if not raw_producto_id.isdigit():
                continue
            producto_id = int(raw_producto_id)
            if producto_id in productos_existentes or producto_id in vistos:
                repetidos.append(producto_id)
            vistos.add(producto_id)

        if not repetidos:
            return []
        return list(
            Producto.objects.filter(id__in=set(repetidos)).order_by("nombre").values_list("nombre", flat=True)
        )

    def _agrupar_requeridos_por_almacen(self):
        requeridos = {}
        for linea in self.resultado_parseo["lineas_stock"]:
            almacen_id = linea["almacen"].id
            producto_id = linea["producto"].id
            requeridos.setdefault(almacen_id, {})
            requeridos[almacen_id][producto_id] = (
                requeridos[almacen_id].get(producto_id, Decimal("0")) + linea["cantidad"]
            )
        return requeridos

    def _primer_almacen_de_item(self, item_index):
        for linea in self.resultado_parseo["lineas_stock"]:
            if linea.get("item_index") == item_index:
                return linea["almacen"]
        lineas = self.resultado_parseo["lineas_stock"]
        return lineas[0]["almacen"] if lineas else self.salida.almacen

    def _guardar_productos(self):
        detalles_por_index = {}
        detalles_validos = self.resultado_parseo["detalles_validos"]
        detalles_meta = self.resultado_parseo["detalles_meta"]

        for index, detalle in enumerate(detalles_validos):
            meta = detalles_meta[index] if index < len(detalles_meta) else {}
            detalle.salida = self.salida
            detalle.almacen = self._primer_almacen_de_item(index)
            producto = getattr(detalle, "producto", None)
            detalle.costo_unitario_aplicado = (
                getattr(producto, "costo_promedio", Decimal("0")) if producto else Decimal("0")
            )
            detalle.presentacion_nombre = meta.get("presentacion_nombre") or "Kilos"
            detalle.presentacion_conversion_id = meta.get("presentacion_id") or "default"
            cantidad_presentacion = meta.get("cantidad_presentacion")
            detalle.cantidad_presentacion = (
                cantidad_presentacion
                if cantidad_presentacion is not None
                else detalle.cantidad
            )
            detalle.presentacion_factor_conversion = meta.get("factor_conversion") or Decimal("1")
            detalle.presentacion_metrica_default = meta.get("metrica_default") or "kg"
            detalle.presentacion_equivalencia_texto = (
                meta.get("equivalencia_texto")
                or f"1 {detalle.presentacion_nombre} = {detalle.presentacion_factor_conversion} {detalle.presentacion_metrica_default}"
            )
            detalle.save()
            detalles_por_index[index] = detalle

        for linea in self.resultado_parseo["lineas_stock"]:
            detalle = detalles_por_index.get(linea.get("item_index"))
            if not detalle:
                continue
            SalidaInventarioDetalleAlmacen.objects.create(
                detalle=detalle,
                almacen=linea["almacen"],
                cantidad=linea["cantidad"],
            )

        requeridos_por_almacen = self._agrupar_requeridos_por_almacen()
        EntradaVirtualVentaService(
            detalles_validos=detalles_validos,
            almacenes_permitidos=self.almacenes_permitidos,
            usuario=self.user if getattr(self.user, "is_authenticated", False) else None,
        ).registrar(
            salida=self.salida,
            requeridos_por_almacen=requeridos_por_almacen,
        )

        for almacen_id, requeridos in requeridos_por_almacen.items():
            aplicar_movimientos_salida(almacen_id=almacen_id, requeridos=requeridos)

        cliente = getattr(self.salida, "cliente_ref", None)
        for detalle in detalles_por_index.values():
            registrar_ultimo_precio_cliente(
                cliente=cliente,
                producto=detalle.producto,
                precio=detalle.precio_unitario,
                usuario=self.user if getattr(self.user, "is_authenticated", False) else None,
                observaciones=f"Producto agregado en nota {self.salida.folio}",
            )

        return list(detalles_por_index.values())
