from decimal import Decimal

from catalogos.services.clientes_precios import registrar_ultimo_precio_cliente
from catalogos.services.credito_clientes import money
from ventas.services.venta_credito import (
    marcar_autorizacion_credito_venta_usada,
    validar_credito_venta,
)
from ventas.services.venta_data import VentaRequestContext
from ventas.services.venta_precio import VentaPrecioMinimoService
from ventas.services.comisiones import calcular_total_con_comision
from ventas.services.marcado import marcar_nota_editada
from ventas.services.pagos import sincronizar_comision_y_pago_terminal


class AjustarPreciosNotaUseCase:
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
