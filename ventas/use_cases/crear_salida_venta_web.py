from dataclasses import dataclass, field

from catalogos.services.credito_clientes import total_detalles_venta
from ventas.services.comisiones import calcular_total_con_comision
from ventas.services.creacion import VentaService
from ventas.services.venta_data import VentaOperacionData, VentaRequestContext
from ventas.services.venta_parser import VentaPostParser


@dataclass
class CrearSalidaVentaWebResultado:
    salida: object = None
    errores: list[str] = field(default_factory=list)

    @property
    def ok(self):
        return self.salida is not None and not self.errores


class CrearSalidaVentaWebUseCase:
    """Adapta el POST web al caso de uso de creación de nota de venta."""

    def __init__(self, *, form, formset, post_data, almacenes_permitidos, request_context):
        self.form = form
        self.formset = formset
        self.post_data = post_data
        self.almacenes_permitidos = almacenes_permitidos
        self.request_context = request_context or VentaRequestContext()

    def execute(self):
        if not self.form.is_valid() or not self.formset.is_valid():
            return CrearSalidaVentaWebResultado(
                errores=["Revisa los datos. Hay campos inválidos."]
            )

        resultado_parseo = VentaPostParser(
            post_data=self.post_data,
            formset=self.formset,
            almacenes_permitidos=self.almacenes_permitidos,
        ).parse()

        if resultado_parseo["errores"]:
            return CrearSalidaVentaWebResultado(errores=resultado_parseo["errores"])

        subtotal_venta = total_detalles_venta(resultado_parseo["detalles_validos"])
        total_venta_validacion = calcular_total_con_comision(
            subtotal_venta,
            forma_pago=self.form.cleaned_data.get("forma_pago_venta"),
        )
        venta_data = VentaOperacionData.from_form(
            self.form,
            request_context=self.request_context,
            total_venta_override=total_venta_validacion,
        )
        venta_service = VentaService(
            data=venta_data,
            detalles_validos=resultado_parseo["detalles_validos"],
            detalles_meta=resultado_parseo["detalles_meta"],
            lineas_stock=resultado_parseo["lineas_stock"],
            almacenes_permitidos=self.almacenes_permitidos,
        )

        errores = venta_service.validar_stock()
        if errores:
            return CrearSalidaVentaWebResultado(errores=errores)

        return CrearSalidaVentaWebResultado(salida=venta_service.guardar())
