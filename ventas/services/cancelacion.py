"""Caso de uso para cancelar notas de venta y retornar inventario."""

from decimal import Decimal

from django.utils import timezone

from ventas.models import NotaVenta
from inventarios.services.stock import aplicar_movimiento_stock


class CancelarNotaVentaService:
    def __init__(self, *, salida, motivo):
        self.salida = salida
        self.motivo = (motivo or "").strip()

    def validar(self):
        errores = []
        if self.salida.estado == NotaVenta.ESTADO_CANCELADA:
            errores.append(f"La nota {self.salida.folio} ya se encontraba cancelada.")
        if not self.motivo:
            errores.append("Captura el motivo de cancelación.")
        return errores

    def execute(self):
        errores = self.validar()
        if errores:
            raise ValueError("; ".join(errores))

        for (producto_id, almacen_id), cantidad in self._calcular_retornos().items():
            aplicar_movimiento_stock(
                producto_id=producto_id,
                almacen_id=almacen_id,
                delta=cantidad,
            )

        self.salida.estado = NotaVenta.ESTADO_CANCELADA
        self.salida.cancelada_en = timezone.now()
        self.salida.motivo_cancelacion = self.motivo
        self.salida.save(update_fields=["estado", "cancelada_en", "motivo_cancelacion"])
        return self.salida

    def _calcular_retornos(self):
        retornos = {}
        for detalle in self.salida.detalles.all():
            asignaciones = list(detalle.asignaciones.all())
            if asignaciones:
                for asignacion in asignaciones:
                    self._sumar_retorno(
                        retornos,
                        producto_id=detalle.producto_id,
                        almacen_id=asignacion.almacen_id,
                        cantidad=asignacion.cantidad,
                    )
            else:
                almacen_id = detalle.almacen_id or self.salida.almacen_id
                if not almacen_id:
                    raise ValueError(
                        f"No se puede cancelar la nota {self.salida.folio}: "
                        f"el detalle {detalle.id} no tiene almacén asociado."
                    )
                self._sumar_retorno(
                    retornos,
                    producto_id=detalle.producto_id,
                    almacen_id=almacen_id,
                    cantidad=detalle.cantidad,
                )
        return retornos

    @staticmethod
    def _sumar_retorno(retornos, *, producto_id, almacen_id, cantidad):
        key = (producto_id, almacen_id)
        retornos[key] = retornos.get(key, Decimal("0")) + cantidad
