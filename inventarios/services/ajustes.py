from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone

from catalogos.models import Producto

from ..models import EntradaInventario, EntradaInventarioDetalle, InventarioStock, SalidaInventario, SalidaInventarioDetalle
from ..utils import decimal_or_default as _to_decimal, decimal_text as _decimal_texto
from .conversiones import normalizar_captura_entrada
from .bitacora import registrar_bitacora_precio_inventario
from .costos import aplicar_entrada_con_costo, costo_promedio_almacen, recalcular_costo_promedio_producto
from .stock import aplicar_movimiento_stock


TIPO_AJUSTE_POSITIVO = "POS"
TIPO_AJUSTE_NEGATIVO = "NEG"


@dataclass(frozen=True)
class AjusteInventarioResultado:
    movimiento: object
    mensaje: str


class AjusteInventarioService:
    """
    Caso de uso para aplicar ajustes de inventario.

    Encapsula la creación del movimiento positivo/negativo, validación de stock,
    conversión a métrica base y afectación de inventario.
    """

    def __init__(self, *, usuario=None):
        self.usuario = usuario if getattr(usuario, "is_authenticated", False) else None

    def aplicar(self, *, data, almacen, conversion_id_raw="") -> AjusteInventarioResultado:
        folio = data["folio"]
        producto = data["producto"]
        cantidad_capturada = data["cantidad"]
        precio_unitario = data["precio_unitario"]
        tipo_ajuste = data["tipo_ajuste"]
        motivo = (data.get("motivo") or "").strip()
        observaciones = (data.get("observaciones") or "").strip()
        observaciones_finales = "\n".join([x for x in [motivo, observaciones] if x]).strip()

        if cantidad_capturada is None or cantidad_capturada <= 0:
            raise ValueError("La cantidad debe ser mayor a 0.")

        self._validar_folio_disponible(folio)

        with transaction.atomic():
            if tipo_ajuste == TIPO_AJUSTE_POSITIVO:
                return self._aplicar_positivo(
                    folio=folio,
                    fecha=data["fecha"],
                    producto=producto,
                    cantidad_capturada=cantidad_capturada,
                    precio_unitario=precio_unitario,
                    almacen=almacen,
                    motivo=motivo,
                    observaciones=observaciones_finales,
                    conversion_id_raw=conversion_id_raw,
                )

            return self._aplicar_negativo(
                folio=folio,
                producto=producto,
                cantidad=cantidad_capturada,
                precio_unitario=precio_unitario,
                almacen=almacen,
                motivo=motivo,
                observaciones=observaciones_finales,
            )

    def preview(self, *, producto_id, almacen_id, tipo_ajuste, cantidad_capturada, conversion_id_raw=""):
        if not str(producto_id or "").isdigit() or not str(almacen_id or "").isdigit():
            return {"ok": False, "message": "Selecciona almacén y producto."}

        producto = Producto.objects.filter(pk=int(producto_id)).first()
        if not producto:
            return {"ok": False, "message": "Producto inválido."}

        cantidad = _to_decimal(cantidad_capturada, default="0")
        equivalencia_texto = ""
        metrica_base = getattr(producto, "metrica", None) or "kg"

        if tipo_ajuste == TIPO_AJUSTE_POSITIVO:
            try:
                captura_entrada = normalizar_captura_entrada(
                    producto=producto,
                    cantidad_capturada=cantidad,
                    conversion_id_raw=conversion_id_raw,
                )
                cantidad = captura_entrada["cantidad_base"]
                equivalencia_texto = captura_entrada["presentacion_equivalencia_texto"]
                metrica_base = captura_entrada["presentacion_metrica_default"]
            except ValueError as exc:
                return {"ok": False, "message": str(exc)}

        stock_actual = self.stock_actual(producto_id=int(producto_id), almacen_id=int(almacen_id))
        delta = cantidad if tipo_ajuste == TIPO_AJUSTE_POSITIVO else -cantidad
        stock_resultante = stock_actual + delta
        permite = cantidad > 0 and stock_resultante >= 0

        costo_promedio = costo_promedio_almacen(producto_id=producto_id, almacen_id=almacen_id)

        if cantidad <= 0:
            message = "Captura una cantidad mayor a 0 para calcular el resultado."
        elif not permite:
            message = "El ajuste dejaría inventario negativo. Reduce la cantidad o selecciona otro almacén."
        else:
            message = "El ajuste puede aplicarse sin dejar inventario negativo."
            if tipo_ajuste == TIPO_AJUSTE_POSITIVO:
                message = f"El ajuste puede aplicarse. Se sumarán {_decimal_texto(cantidad)} {metrica_base} al inventario."

        return {
            "ok": True,
            "stock_actual": str(stock_actual),
            "stock_resultante": str(stock_resultante),
            "cantidad": str(cantidad),
            "cantidad_capturada": str(_to_decimal(cantidad_capturada, default="0")),
            "equivalencia_texto": equivalencia_texto,
            "metrica_base": metrica_base,
            "costo_promedio": str(costo_promedio),
            "permite": permite,
            "message": message,
        }

    @staticmethod
    def stock_actual(*, producto_id, almacen_id):
        stock_row = InventarioStock.objects.filter(
            producto_id=producto_id,
            almacen_id=almacen_id,
        ).first()
        return _to_decimal(stock_row.cantidad if stock_row else 0)

    @staticmethod
    def _validar_folio_disponible(folio):
        if EntradaInventario.objects.filter(folio=folio).exists() or SalidaInventario.objects.filter(folio=folio).exists():
            raise ValueError(f"El folio {folio} ya existe. Intenta nuevamente.")

    def _aplicar_positivo(self, *, folio, fecha, producto, cantidad_capturada, precio_unitario, almacen, motivo, observaciones, conversion_id_raw):
        captura_entrada = normalizar_captura_entrada(
            producto=producto,
            cantidad_capturada=cantidad_capturada,
            conversion_id_raw=conversion_id_raw,
        )
        cantidad = captura_entrada["cantidad_base"]

        entrada = EntradaInventario.objects.create(
            folio=folio,
            fecha=fecha,
            proveedor=None,
            tipo=EntradaInventario.TIPO_AJUSTE_POSITIVO,
            motivo=motivo,
            observaciones=observaciones,
            almacen=almacen,
            registrado_por=self.usuario,
        )

        EntradaInventarioDetalle.objects.create(
            entrada=entrada,
            producto=producto,
            almacen=almacen,
            presentacion_nombre=captura_entrada["presentacion_nombre"],
            presentacion_conversion_id=captura_entrada["presentacion_conversion_id"],
            cantidad_presentacion=captura_entrada["cantidad_presentacion"],
            presentacion_factor_conversion=captura_entrada["presentacion_factor_conversion"],
            presentacion_metrica_default=captura_entrada["presentacion_metrica_default"],
            presentacion_equivalencia_texto=captura_entrada["presentacion_equivalencia_texto"],
            cantidad=cantidad,
            costo_unitario=precio_unitario,
            costo_total=cantidad * precio_unitario,
        )

        aplicar_entrada_con_costo(
            producto_id=producto.pk,
            almacen_id=almacen.id,
            cantidad=cantidad,
            costo_unitario=precio_unitario,
        )
        registrar_bitacora_precio_inventario(
            producto=producto,
            usuario=self.usuario,
            motivo="Ajuste positivo de inventario",
        )

        return AjusteInventarioResultado(
            movimiento=entrada,
            mensaje=f"Ajuste positivo aplicado en {almacen}. Folio: {folio}",
        )

    def _aplicar_negativo(self, *, folio, producto, cantidad, precio_unitario, almacen, motivo, observaciones):
        fecha = timezone.localdate()
        stock_row = InventarioStock.objects.select_for_update().filter(
            producto_id=producto.pk,
            almacen_id=almacen.id,
        ).first()
        stock_actual = _to_decimal(stock_row.cantidad if stock_row else 0)

        if stock_actual < cantidad:
            raise ValueError(
                f"Stock insuficiente para '{producto}'. Disponible en {almacen}: {stock_actual} | Requerido: {cantidad}"
            )

        salida = SalidaInventario.objects.create(
            folio=folio,
            fecha=fecha,
            proveedor="",
            tipo=SalidaInventario.TIPO_AJUSTE_NEGATIVO,
            motivo=motivo,
            observaciones=observaciones,
            almacen=almacen,
            registrado_por=self.usuario,
        )

        SalidaInventarioDetalle.objects.create(
            salida=salida,
            producto=producto,
            almacen=almacen,
            cantidad=cantidad,
            precio_unitario=precio_unitario,
            costo_unitario_aplicado=getattr(producto, "costo_promedio", 0) or 0,
        )

        aplicar_movimiento_stock(
            producto_id=producto.pk,
            almacen_id=almacen.id,
            delta=-cantidad,
        )
        recalcular_costo_promedio_producto(producto.pk)
        registrar_bitacora_precio_inventario(
            producto=producto,
            usuario=self.usuario,
            motivo="Ajuste negativo de inventario",
        )

        return AjusteInventarioResultado(
            movimiento=salida,
            mensaje=f"Ajuste negativo aplicado en {almacen}. Folio: {folio}",
        )
