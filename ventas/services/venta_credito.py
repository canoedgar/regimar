from catalogos.services.credito_clientes import (
    marcar_autorizacion_credito_usada,
    total_detalles_venta,
    validar_credito_cliente_para_venta,
)


class VentaCreditoService:
    """
    Caso de uso para validación y consumo de autorizaciones de crédito.

    Mantiene fuera de VentaService la dependencia directa con cartera/catálogo y
    deja en un solo punto el cálculo del total de venta cuando se valida crédito.
    """

    def __init__(
        self,
        *,
        cliente,
        fecha_venta=None,
        contexto=None,
        venta_existente=None,
        total_venta_override=None,
        validar_credito=True,
    ):
        self.cliente = cliente
        self.fecha_venta = fecha_venta
        self.contexto = contexto
        self.venta_existente = venta_existente
        self.total_venta_override = total_venta_override
        self.validar_credito = validar_credito
        self.autorizacion = None

    def validar(self, detalles_validos=None):
        if not self.validar_credito or not self.cliente:
            return []

        total_venta = (
            self.total_venta_override
            if self.total_venta_override is not None
            else total_detalles_venta(detalles_validos or [])
        )

        errores, autorizacion = validar_credito_cliente_para_venta(
            cliente=self.cliente,
            total_venta=total_venta,
            fecha_venta=self.fecha_venta,
            request=getattr(self.contexto, "credito_request", None),
            venta_existente=self.venta_existente,
        )
        self.autorizacion = autorizacion
        return errores

    def marcar_usada(self, venta):
        return marcar_autorizacion_credito_usada(self.autorizacion, venta)


def validar_credito_venta(
    *,
    cliente,
    total_venta,
    fecha_venta=None,
    contexto=None,
    venta_existente=None,
):
    """Helper explícito para flujos que ya tienen el total calculado."""
    service = VentaCreditoService(
        cliente=cliente,
        fecha_venta=fecha_venta,
        contexto=contexto,
        venta_existente=venta_existente,
        total_venta_override=total_venta,
    )
    errores = service.validar()
    return errores, service.autorizacion


def marcar_autorizacion_credito_venta_usada(autorizacion, venta):
    return marcar_autorizacion_credito_usada(autorizacion, venta)
