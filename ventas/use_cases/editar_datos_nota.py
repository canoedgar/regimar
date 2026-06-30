from ventas.services.venta_credito import (
    marcar_autorizacion_credito_venta_usada,
    validar_credito_venta,
)
from ventas.services.venta_data import VentaRequestContext
from ventas.services.comisiones import calcular_total_con_comision, get_subtotal_nota
from ventas.services.marcado import marcar_nota_editada
from ventas.services.pagos import sincronizar_comision_y_pago_terminal


class EditarDatosNotaUseCase:
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
        salida.save()
        marcar_nota_editada(salida, self.user)
        sincronizar_comision_y_pago_terminal(salida, self.user)
        marcar_autorizacion_credito_venta_usada(self.autorizacion_credito, salida)
        return salida
