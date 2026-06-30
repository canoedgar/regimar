from ventas.services.pagos import sincronizar_comision_y_pago_terminal


class PagoTerminalVentaAdapter:
    def sincronizar_terminal(self, salida, *, usuario=None):
        return sincronizar_comision_y_pago_terminal(
            salida,
            usuario=usuario,
        )
