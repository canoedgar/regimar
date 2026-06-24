from django.db import models

from inventarios.models import SalidaInventario, SalidaInventarioDetalle


class NotaVentaManager(models.Manager):
    """Manager comercial que expone únicamente salidas de tipo venta."""

    def get_queryset(self):
        return super().get_queryset().filter(tipo=SalidaInventario.TIPO_VENTA)


class NotaVentaDetalleManager(models.Manager):
    """Manager comercial que expone únicamente detalles de notas de venta."""

    def get_queryset(self):
        return super().get_queryset().filter(salida__tipo=SalidaInventario.TIPO_VENTA)


class NotaVenta(SalidaInventario):
    """
    Proxy comercial de SalidaInventario.

    Fase 1 de separación: la tabla física sigue siendo la de inventarios para no
    romper cartera, costos, kardex ni migraciones existentes. El dominio de
    ventas comienza a operar con un nombre propio y permisos/contenido propios.
    """

    objects = NotaVentaManager()

    class Meta:
        proxy = True
        verbose_name = "Nota de venta"
        verbose_name_plural = "Notas de venta"


class NotaVentaDetalle(SalidaInventarioDetalle):
    """
    Proxy comercial del detalle de salida por venta.

    Permite que ventas tenga un lenguaje de dominio propio mientras inventarios
    conserva el registro de afectación física de stock.
    """

    objects = NotaVentaDetalleManager()

    class Meta:
        proxy = True
        verbose_name = "Detalle de nota de venta"
        verbose_name_plural = "Detalles de notas de venta"
