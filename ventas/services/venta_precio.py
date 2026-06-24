from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from catalogos.models import ClienteProductoPrecio, PrecioMenorMinimoAutorizacion
from ventas.services.venta_notificaciones import VentaPrecioMinimoNotificacionService


class VentaPrecioMinimoService:
    """
    Caso de uso para validar precio mínimo y crear solicitudes de autorización.

    La venta solo pregunta por errores; este servicio concentra la regla de
    precio autorizado por cliente/producto, creación de token y notificación.
    """

    def __init__(self, *, cliente=None, contexto=None, notificador=None):
        self.cliente = cliente
        self.contexto = contexto
        self.notificador = notificador or VentaPrecioMinimoNotificacionService()

    def validar_detalles(self, *, detalles_validos, productos_por_id):
        errores = []

        for detalle in detalles_validos or []:
            producto = productos_por_id.get(detalle.producto_id)
            if not producto:
                continue

            error = self.validar_detalle(detalle=detalle, producto=producto)
            if error:
                errores.append(error)

        return errores

    def validar_detalle(self, *, detalle, producto):
        precio_minimo = getattr(producto, "precio_minimo", Decimal("0")) or Decimal("0")
        precio_unitario = detalle.precio_unitario or Decimal("0")

        if precio_minimo <= 0 or precio_unitario >= precio_minimo:
            return None

        if self.precio_ya_autorizado(producto=producto, precio=precio_unitario):
            return None

        envio_confirmado = bool(
            getattr(self.contexto, "confirmar_envio_autorizacion_precio", False)
        )
        autorizacion = None

        if envio_confirmado:
            autorizacion = self.crear_autorizacion(
                producto=producto,
                precio_solicitado=precio_unitario,
            )

        extra = ""
        if autorizacion:
            extra = " Se envió solicitud de autorización a administradores activos."
        elif not envio_confirmado:
            extra = " Confirma el envío de la solicitud de autorización antes de continuar."

        return (
            f"{producto.nombre}: el precio solicitado ${precio_unitario} "
            f"es menor al mínimo autorizado ${precio_minimo}.{extra}"
        )

    def precio_ya_autorizado(self, *, producto, precio):
        if not self.cliente:
            return False
        return ClienteProductoPrecio.objects.filter(
            cliente=self.cliente,
            producto=producto,
            ultimo_precio=precio,
        ).exists()

    def crear_autorizacion(self, *, producto, precio_solicitado):
        if not self.cliente:
            return None

        autorizacion = PrecioMenorMinimoAutorizacion.objects.create(
            cliente=self.cliente,
            producto=producto,
            usuario_solicita=getattr(self.contexto, "usuario", None),
            precio_actual=getattr(producto, "precio", Decimal("0")) or Decimal("0"),
            precio_minimo=getattr(producto, "precio_minimo", Decimal("0")) or Decimal("0"),
            precio_solicitado=precio_solicitado,
            expira_en=timezone.now() + timedelta(hours=24),
        )
        self.notificador.enviar_solicitud(
            autorizacion=autorizacion,
            contexto=self.contexto,
        )
        return autorizacion
