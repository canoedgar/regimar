from dataclasses import dataclass
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from ..models import (
    EntradaInventario,
    EntradaInventarioDetalle,
    InventarioStock,
    SalidaInventario,
    SalidaInventarioDetalle,
)
from ..utils import decimal_or_default as _to_decimal
from .folios import folio_reversa_unico
from .bitacora import registrar_bitacora_precio_inventario
from .costos import aplicar_entrada_con_costo, recalcular_costo_promedio_producto
from .stock import aplicar_movimiento_stock


@dataclass(frozen=True)
class ReversaInventarioResultado:
    movimiento_original: object
    movimiento_reversa: object
    folio: str
    mensaje: str


class ReversaInventarioService:
    """
    Caso de uso para reversar movimientos de inventario.

    Mantiene una sola regla para marcadores de reversa, validación de stock y
    creación del movimiento compensatorio.
    """

    def __init__(self, *, usuario=None):
        self.usuario = usuario if getattr(usuario, "is_authenticated", False) else None

    @staticmethod
    def marcador_reversa_entrada_manual(entrada_id):
        return f"REVERSA_DE=entrada_manual:{entrada_id}"

    @classmethod
    def entrada_manual_esta_reversada(cls, entrada_id):
        return SalidaInventario.objects.filter(
            observaciones__icontains=cls.marcador_reversa_entrada_manual(entrada_id)
        ).exists()

    @staticmethod
    def entrada_es_reversa(entrada):
        return "REVERSA_DE=" in (entrada.observaciones or "")

    @staticmethod
    def ajuste_esta_reversado(tipo, movimiento_id):
        marcador = f"REVERSA_DE={tipo}:{movimiento_id}"
        return (
            EntradaInventario.objects.filter(observaciones__icontains=marcador).exists()
            or SalidaInventario.objects.filter(observaciones__icontains=marcador).exists()
        )

    def reversar_entrada_manual(self, *, entrada_id) -> ReversaInventarioResultado:
        if self.entrada_manual_esta_reversada(entrada_id):
            raise ValueError("Esta entrada manual ya tiene una reversa registrada.")

        with transaction.atomic():
            try:
                entrada = (
                    EntradaInventario.objects
                    .select_for_update()
                    .prefetch_related("detalles__producto", "detalles__almacen")
                    .get(pk=entrada_id, tipo=EntradaInventario.TIPO_ENTRADA_MANUAL)
                )
            except EntradaInventario.DoesNotExist as exc:
                raise ValueError("Entrada manual no encontrada.") from exc

            if self.entrada_es_reversa(entrada):
                raise IntegrityError("No se puede reversar una entrada que ya corresponde a una reversa automática.")

            detalles = list(entrada.detalles.select_related("producto", "almacen"))
            if not detalles:
                raise IntegrityError("La entrada manual no tiene detalle para reversar.")

            self._validar_stock_para_reversar_entrada(entrada=entrada, detalles=detalles)

            folio = folio_reversa_unico(prefix="REV", folio_original=entrada.folio, movimiento_id=entrada.id)
            marcador = self.marcador_reversa_entrada_manual(entrada.id)
            salida = SalidaInventario.objects.create(
                folio=folio,
                fecha=timezone.localdate(),
                proveedor="",
                tipo=SalidaInventario.TIPO_AJUSTE_NEGATIVO,
                motivo="Reversa de entrada manual",
                observaciones=f"Reversa automática de la entrada manual {entrada.folio}.\n{marcador}",
                almacen=entrada.almacen,
                registrado_por=self.usuario,
            )

            productos_recalculados = set()
            for detalle in detalles:
                almacen = detalle.almacen or entrada.almacen
                cantidad = _to_decimal(detalle.cantidad)
                costo_unitario = _to_decimal(detalle.costo_unitario)

                SalidaInventarioDetalle.objects.create(
                    salida=salida,
                    producto=detalle.producto,
                    almacen=almacen,
                    presentacion_nombre=detalle.presentacion_nombre,
                    presentacion_conversion_id=detalle.presentacion_conversion_id,
                    cantidad_presentacion=detalle.cantidad_presentacion,
                    presentacion_factor_conversion=detalle.presentacion_factor_conversion,
                    presentacion_metrica_default=detalle.presentacion_metrica_default,
                    presentacion_equivalencia_texto=detalle.presentacion_equivalencia_texto,
                    cantidad=cantidad,
                    precio_unitario=costo_unitario,
                    costo_unitario_aplicado=costo_unitario,
                )

                aplicar_movimiento_stock(
                    producto_id=detalle.producto_id,
                    almacen_id=almacen.id,
                    delta=-cantidad,
                )
                productos_recalculados.add(detalle.producto_id)

            for producto_id in productos_recalculados:
                recalcular_costo_promedio_producto(producto_id)

        return ReversaInventarioResultado(
            movimiento_original=entrada,
            movimiento_reversa=salida,
            folio=folio,
            mensaje=f"Se reversó la entrada manual {entrada.folio} con la salida {folio}.",
        )

    def reversar_ajuste(self, *, tipo, movimiento_id) -> ReversaInventarioResultado:
        if tipo not in {"entrada", "salida"}:
            raise ValueError("Tipo de ajuste inválido.")

        if self.ajuste_esta_reversado(tipo, movimiento_id):
            raise ValueError("Este ajuste ya tiene una reversa registrada.")

        with transaction.atomic():
            if tipo == "entrada":
                return self._reversar_ajuste_positivo(movimiento_id)
            return self._reversar_ajuste_negativo(movimiento_id)

    @staticmethod
    def _validar_stock_para_reversar_entrada(*, entrada, detalles):
        acumulado = {}
        for detalle in detalles:
            almacen = detalle.almacen or entrada.almacen
            if not almacen:
                raise IntegrityError(f"El producto {detalle.producto} no tiene almacén definido.")

            cantidad = _to_decimal(detalle.cantidad)
            if cantidad <= 0:
                raise IntegrityError(f"El producto {detalle.producto} tiene cantidad inválida para reversar.")

            key = (detalle.producto_id, almacen.id)
            acumulado[key] = acumulado.get(key, Decimal("0")) + cantidad

        for (producto_id, almacen_id), cantidad_total in acumulado.items():
            stock_row = InventarioStock.objects.select_for_update().filter(
                producto_id=producto_id,
                almacen_id=almacen_id,
            ).first()
            stock_actual = _to_decimal(stock_row.cantidad if stock_row else 0)
            if stock_actual < cantidad_total:
                raise IntegrityError(
                    f"No se puede reversar porque dejaría inventario negativo. "
                    f"Producto ID {producto_id}, almacén ID {almacen_id}. "
                    f"Disponible: {stock_actual}, requerido: {cantidad_total}."
                )

    def _reversar_ajuste_positivo(self, movimiento_id):
        try:
            entrada_original = EntradaInventario.objects.select_for_update().get(
                pk=movimiento_id,
                tipo=EntradaInventario.TIPO_AJUSTE_POSITIVO,
            )
        except EntradaInventario.DoesNotExist as exc:
            raise ValueError("Ajuste positivo no encontrado.") from exc

        detalle = entrada_original.detalles.select_related("producto", "almacen").first()
        if not detalle:
            raise IntegrityError("El ajuste positivo no tiene detalle para reversar.")

        almacen = detalle.almacen or entrada_original.almacen
        if not almacen:
            raise IntegrityError("El ajuste positivo no tiene almacén definido.")

        stock_row = InventarioStock.objects.select_for_update().filter(
            producto_id=detalle.producto_id,
            almacen_id=almacen.id,
        ).first()
        stock_actual = _to_decimal(stock_row.cantidad if stock_row else 0)
        cantidad = _to_decimal(detalle.cantidad)
        if stock_actual < cantidad:
            raise IntegrityError(
                f"No se puede deshacer porque dejaría inventario negativo. Disponible: {stock_actual}, requerido: {cantidad}."
            )

        folio = folio_reversa_unico(prefix="REV", folio_original=entrada_original.folio, movimiento_id=entrada_original.id)
        marcador = f"REVERSA_DE=entrada:{entrada_original.id}"
        salida = SalidaInventario.objects.create(
            folio=folio,
            fecha=timezone.localdate(),
            proveedor="",
            tipo=SalidaInventario.TIPO_AJUSTE_NEGATIVO,
            motivo="Reversa de ajuste positivo",
            observaciones=f"Reversa automática del ajuste {entrada_original.folio}.\n{marcador}",
            almacen=almacen,
            registrado_por=self.usuario,
        )
        SalidaInventarioDetalle.objects.create(
            salida=salida,
            producto=detalle.producto,
            almacen=almacen,
            presentacion_nombre=detalle.presentacion_nombre,
            presentacion_conversion_id=detalle.presentacion_conversion_id,
            cantidad_presentacion=detalle.cantidad_presentacion,
            presentacion_factor_conversion=detalle.presentacion_factor_conversion,
            presentacion_metrica_default=detalle.presentacion_metrica_default,
            presentacion_equivalencia_texto=detalle.presentacion_equivalencia_texto,
            cantidad=cantidad,
            precio_unitario=detalle.costo_unitario,
            costo_unitario_aplicado=getattr(detalle.producto, "costo_promedio", 0) or 0,
        )
        aplicar_movimiento_stock(producto_id=detalle.producto_id, almacen_id=almacen.id, delta=-cantidad)
        recalcular_costo_promedio_producto(detalle.producto_id)

        return ReversaInventarioResultado(
            movimiento_original=entrada_original,
            movimiento_reversa=salida,
            folio=folio,
            mensaje=f"Se reversó el ajuste positivo {entrada_original.folio} con la salida {folio}.",
        )

    def _reversar_ajuste_negativo(self, movimiento_id):
        try:
            salida_original = SalidaInventario.objects.select_for_update().get(
                pk=movimiento_id,
                tipo=SalidaInventario.TIPO_AJUSTE_NEGATIVO,
            )
        except SalidaInventario.DoesNotExist as exc:
            raise ValueError("Ajuste negativo no encontrado.") from exc

        detalle = salida_original.detalles.select_related("producto", "almacen").first()
        if not detalle:
            raise IntegrityError("El ajuste negativo no tiene detalle para reversar.")

        almacen = detalle.almacen or salida_original.almacen
        if not almacen:
            raise IntegrityError("El ajuste negativo no tiene almacén definido.")

        cantidad = _to_decimal(detalle.cantidad)
        costo_reversa = _to_decimal(detalle.costo_unitario_aplicado or detalle.precio_unitario)
        folio = folio_reversa_unico(prefix="REV", folio_original=salida_original.folio, movimiento_id=salida_original.id)
        marcador = f"REVERSA_DE=salida:{salida_original.id}"
        entrada = EntradaInventario.objects.create(
            folio=folio,
            fecha=timezone.localdate(),
            proveedor=None,
            tipo=EntradaInventario.TIPO_AJUSTE_POSITIVO,
            motivo="Reversa de ajuste negativo",
            observaciones=f"Reversa automática del ajuste {salida_original.folio}.\n{marcador}",
            almacen=almacen,
            registrado_por=self.usuario,
        )
        EntradaInventarioDetalle.objects.create(
            entrada=entrada,
            producto=detalle.producto,
            almacen=almacen,
            presentacion_nombre=detalle.presentacion_nombre,
            presentacion_conversion_id=detalle.presentacion_conversion_id,
            cantidad_presentacion=detalle.cantidad_presentacion,
            presentacion_factor_conversion=detalle.presentacion_factor_conversion,
            presentacion_metrica_default=detalle.presentacion_metrica_default,
            presentacion_equivalencia_texto=detalle.presentacion_equivalencia_texto,
            cantidad=cantidad,
            costo_unitario=costo_reversa,
            costo_total=cantidad * costo_reversa,
        )
        aplicar_entrada_con_costo(
            producto_id=detalle.producto_id,
            almacen_id=almacen.id,
            cantidad=cantidad,
            costo_unitario=costo_reversa,
        )
        registrar_bitacora_precio_inventario(
            producto=detalle.producto,
            usuario=self.usuario,
            motivo="Reversa de ajuste negativo de inventario",
        )

        return ReversaInventarioResultado(
            movimiento_original=salida_original,
            movimiento_reversa=entrada,
            folio=folio,
            mensaje=f"Se reversó el ajuste negativo {salida_original.folio} con la entrada {folio}.",
        )
