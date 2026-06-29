from ventas.services.comisiones import aplicar_comision_terminal, es_nota_terminal


def _usuario_autenticado_o_none(usuario):
    return usuario if getattr(usuario, "is_authenticated", False) else None


def sincronizar_comision_y_pago_terminal(salida, usuario=None):
    """Aplica comisión de terminal y sincroniza el pago automático cuando corresponde."""
    aplicar_comision_terminal(salida)
    if not es_nota_terminal(salida):
        return None

    from cartera.models import PagoMetodoDetalle
    from cartera.services.cartera import sincronizar_pago_automatico_nota_pagada

    return sincronizar_pago_automatico_nota_pagada(
        salida,
        usuario=_usuario_autenticado_o_none(usuario),
        metodo=PagoMetodoDetalle.METODO_TARJETA,
        fecha_pago=salida.fecha,
    )
