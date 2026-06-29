from ventas.services.venta_credito import VentaCreditoService
from ventas.services.venta_data import VentaOperacionData, VentaRequestContext
from ventas.services.venta_precio import VentaPrecioMinimoService
from ventas.services.validacion import ValidarNotaVentaService
from ventas.use_cases.crear_nota_venta import CrearNotaVentaUseCase


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
        return ValidarNotaVentaService(
            detalles_validos=self.detalles_validos,
            lineas_stock=self.lineas_stock,
            almacenes_permitidos=self.almacenes_permitidos,
            credito_service=self.credito_service,
            precio_service=self.precio_service,
        ).validar()

    def guardar(self):
        return CrearNotaVentaUseCase(
            data=self.data,
            detalles_validos=self.detalles_validos,
            detalles_meta=self.detalles_meta,
            lineas_stock=self.lineas_stock,
            almacenes_permitidos=self.almacenes_permitidos,
            credito_service=self.credito_service,
        ).execute()

