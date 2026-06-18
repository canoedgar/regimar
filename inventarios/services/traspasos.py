from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import F

from catalogos.models import Producto

from ..models import (
    EntradaInventario,
    EntradaInventarioDetalle,
    InventarioStock,
    SalidaInventario,
    SalidaInventarioDetalle,
)
from .stock import aplicar_movimiento_stock, recalcular_costo_promedio_producto


def _to_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


@dataclass(frozen=True)
class TraspasoInventarioResultado:
    salida: SalidaInventario
    entrada: EntradaInventario


class TraspasoInventarioService:
    """
    Caso de uso para traspasar inventario entre almacenes.
    Centraliza validaciones, creación de movimientos y afectación de stock.
    """

    def __init__(self, *, usuario=None):
        self.usuario = usuario if getattr(usuario, "is_authenticated", False) else None

    def ejecutar(self, *, data) -> TraspasoInventarioResultado:
        with transaction.atomic():
            producto = data["producto"]
            origen = data["almacen_origen"]
            destino = data["almacen_destino"]
            cantidad = _to_decimal(data["cantidad"])
            fecha = data["fecha"]
            folio_salida = data["folio_salida"]
            folio_entrada = data["folio_entrada"]
            motivo = (data.get("motivo") or "").strip()
            observaciones = (data.get("observaciones") or "").strip()

            self._validar_operacion(
                producto=producto,
                origen=origen,
                destino=destino,
                cantidad=cantidad,
                folio_salida=folio_salida,
                folio_entrada=folio_entrada,
            )

            stock_origen = (
                InventarioStock.objects
                .select_for_update()
                .filter(producto=producto, almacen=origen)
                .first()
            )
            disponible_origen = _to_decimal(stock_origen.cantidad if stock_origen else 0)
            if disponible_origen < cantidad:
                raise IntegrityError(
                    f"Stock insuficiente para '{producto}'. Disponible en {origen}: {disponible_origen} | Requerido: {cantidad}"
                )

            costo_origen = _to_decimal(getattr(stock_origen, "costo_promedio", 0) if stock_origen else 0)
            observaciones_base = "\n".join([x for x in [motivo, observaciones] if x]).strip()

            salida = SalidaInventario.objects.create(
                folio=folio_salida,
                fecha=fecha,
                tipo=SalidaInventario.TIPO_TRASLADO_SALIDA,
                proveedor="",
                motivo=motivo,
                observaciones=observaciones_base,
                almacen=origen,
                almacen_origen=origen,
                almacen_destino=destino,
                registrado_por=self.usuario,
            )
            entrada = EntradaInventario.objects.create(
                folio=folio_entrada,
                fecha=fecha,
                proveedor=None,
                tipo=EntradaInventario.TIPO_TRASLADO,
                motivo=motivo,
                observaciones=observaciones_base,
                almacen=destino,
                almacen_origen=origen,
                almacen_destino=destino,
                registrado_por=self.usuario,
            )

            salida.documento_referencia = entrada.folio
            salida.observaciones = self._append_pair_marker(
                salida.observaciones,
                f"TRASPASO_ENTRADA={entrada.id}:{entrada.folio}",
            )
            salida.save(update_fields=["documento_referencia", "observaciones"])

            entrada.documento_referencia = salida.folio
            entrada.observaciones = self._append_pair_marker(
                entrada.observaciones,
                f"TRASPASO_SALIDA={salida.id}:{salida.folio}",
            )
            entrada.save(update_fields=["documento_referencia", "observaciones"])

            SalidaInventarioDetalle.objects.create(
                salida=salida,
                producto=producto,
                almacen=origen,
                cantidad=cantidad,
                precio_unitario=costo_origen,
                costo_unitario_aplicado=costo_origen,
            )
            EntradaInventarioDetalle.objects.create(
                entrada=entrada,
                producto=producto,
                almacen=destino,
                cantidad=cantidad,
                costo_unitario=costo_origen,
                costo_total=cantidad * costo_origen,
                presentacion_nombre=getattr(producto, "metrica", None) or "Base",
                presentacion_conversion_id="traspaso",
                cantidad_presentacion=cantidad,
                presentacion_factor_conversion=Decimal("1"),
                presentacion_metrica_default=getattr(producto, "metrica", None) or "",
                presentacion_equivalencia_texto="Traspaso entre almacenes",
            )

            aplicar_movimiento_stock(
                producto_id=producto.pk,
                almacen_id=origen.pk,
                delta=-cantidad,
            )
            self._aplicar_entrada_traspaso_con_costo(
                producto_id=producto.pk,
                almacen_id=destino.pk,
                cantidad=cantidad,
                costo_unitario=costo_origen,
            )
            recalcular_costo_promedio_producto(producto.pk)

            return TraspasoInventarioResultado(salida=salida, entrada=entrada)

    def _validar_operacion(self, *, producto, origen, destino, cantidad, folio_salida, folio_entrada):
        if not producto:
            raise IntegrityError("Selecciona un producto para traspasar.")
        if not origen or not destino:
            raise IntegrityError("Selecciona almacén origen y almacén destino.")
        if origen.pk == destino.pk:
            raise IntegrityError("El almacén destino debe ser diferente al almacén origen.")
        if cantidad <= 0:
            raise IntegrityError("La cantidad debe ser mayor a 0.")
        if not getattr(origen, "permite_transferencias", False):
            raise IntegrityError("El almacén origen no permite transferencias.")
        if not getattr(destino, "permite_transferencias", False):
            raise IntegrityError("El almacén destino no permite transferencias.")
        if EntradaInventario.objects.filter(folio=folio_entrada).exists() or SalidaInventario.objects.filter(folio=folio_entrada).exists():
            raise IntegrityError(f"El folio {folio_entrada} ya existe. Intenta nuevamente.")
        if EntradaInventario.objects.filter(folio=folio_salida).exists() or SalidaInventario.objects.filter(folio=folio_salida).exists():
            raise IntegrityError(f"El folio {folio_salida} ya existe. Intenta nuevamente.")

    @staticmethod
    def _append_pair_marker(observaciones, marker):
        observaciones = (observaciones or "").strip()
        return f"{observaciones}\n{marker}" if observaciones else marker

    @staticmethod
    def _aplicar_entrada_traspaso_con_costo(*, producto_id, almacen_id, cantidad, costo_unitario):
        cantidad = _to_decimal(cantidad)
        costo_unitario = _to_decimal(costo_unitario)
        if cantidad <= 0:
            return

        stock_row, _ = InventarioStock.objects.select_for_update().get_or_create(
            producto_id=producto_id,
            almacen_id=almacen_id,
            defaults={"cantidad": Decimal("0"), "costo_promedio": Decimal("0")},
        )

        cantidad_actual = _to_decimal(stock_row.cantidad)
        costo_actual = _to_decimal(stock_row.costo_promedio)
        nueva_cantidad = cantidad_actual + cantidad
        valor_actual = cantidad_actual * costo_actual
        valor_entrada = cantidad * costo_unitario
        nuevo_costo = Decimal("0")
        if nueva_cantidad > 0:
            nuevo_costo = (valor_actual + valor_entrada) / nueva_cantidad

        stock_row.cantidad = nueva_cantidad
        stock_row.costo_promedio = nuevo_costo
        stock_row.save(update_fields=["cantidad", "costo_promedio"])

        Producto.objects.filter(pk=producto_id).update(stock=F("stock") + cantidad)
