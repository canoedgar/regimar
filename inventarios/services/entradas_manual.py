import json
from dataclasses import dataclass
from decimal import Decimal

from django.db import IntegrityError, transaction

from catalogos.models import Producto

from ..models import EntradaInventario, EntradaInventarioDetalle
from ..utils import decimal_or_default as _to_decimal, decimal_text as _decimal_texto
from .conversiones import normalizar_captura_entrada
from .bitacora import registrar_bitacora_precio_inventario
from .costos import aplicar_entrada_con_costo


@dataclass(frozen=True)
class EntradaManualResultado:
    entrada: EntradaInventario


class EntradaManualInventarioService:
    """
    Caso de uso para registrar entradas manuales de inventario.

    La vista solo valida el formulario y delega aquí la interpretación del
    detalle, creación de movimientos y afectación de stock.
    """

    def __init__(self, *, usuario=None):
        self.usuario = usuario if getattr(usuario, "is_authenticated", False) else None

    def registrar_desde_form(self, *, form, detalle_json) -> EntradaManualResultado:
        detalle_norm = self.normalizar_detalle(detalle_json)

        with transaction.atomic():
            entrada = form.save(commit=False)
            entrada.tipo = EntradaInventario.TIPO_ENTRADA_MANUAL
            entrada.registrado_por = self.usuario
            entrada.save()

            for linea in detalle_norm:
                EntradaInventarioDetalle.objects.create(
                    entrada=entrada,
                    producto_id=linea["producto_id"],
                    almacen_id=linea["almacen_id"],
                    presentacion_nombre=linea["presentacion_nombre"],
                    presentacion_conversion_id=linea["presentacion_conversion_id"],
                    cantidad_presentacion=linea["cantidad_presentacion"],
                    presentacion_factor_conversion=linea["presentacion_factor_conversion"],
                    presentacion_metrica_default=linea["presentacion_metrica_default"],
                    presentacion_equivalencia_texto=linea["presentacion_equivalencia_texto"],
                    cantidad=linea["cantidad"],
                    costo_unitario=linea["costo_unitario"],
                    es_peso_variable=linea["es_peso_variable"],
                    cantidad_cajas=linea["cantidad_cajas"],
                    kilos_reales=linea["kilos_reales"],
                    costo_total=linea["costo_total"],
                )

                aplicar_entrada_con_costo(
                    producto_id=linea["producto_id"],
                    almacen_id=linea["almacen_id"],
                    cantidad=linea["cantidad"],
                    costo_unitario=linea["costo_unitario"],
                )
                registrar_bitacora_precio_inventario(
                    producto_id=linea["producto_id"],
                    usuario=self.usuario,
                    motivo="Entrada manual de inventario",
                )

        return EntradaManualResultado(entrada=entrada)

    def normalizar_detalle(self, detalle_json):
        detalle = self._cargar_detalle(detalle_json)
        if not detalle:
            raise ValueError("Debes agregar al menos un producto.")

        detalle_norm = []
        for indice, linea in enumerate(detalle, start=1):
            detalle_norm.append(self._normalizar_linea(indice, linea))

        return detalle_norm

    @staticmethod
    def _cargar_detalle(detalle_json):
        if isinstance(detalle_json, list):
            return detalle_json

        try:
            detalle = json.loads(detalle_json or "[]")
        except Exception as exc:
            raise ValueError("No fue posible interpretar el detalle de productos.") from exc

        if not isinstance(detalle, list):
            raise ValueError("No fue posible interpretar el detalle de productos.")

        return detalle

    def _normalizar_linea(self, indice, linea):
        try:
            producto_id = int(linea.get("producto_id"))
            almacen_id = int(linea.get("almacen_id"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Línea {indice}: producto o almacén inválido.") from exc

        producto = Producto.objects.filter(id=producto_id).first()
        if not producto:
            raise ValueError(f"Línea {indice}: producto inválido.")

        costo_unitario = _to_decimal(linea.get("costo_unitario"))
        if costo_unitario < 0:
            raise ValueError(f"Línea {indice}: el costo unitario no puede ser negativo.")

        if bool(getattr(producto, "maneja_peso_variable", False)):
            return self._normalizar_linea_peso_variable(
                indice=indice,
                linea=linea,
                producto=producto,
                producto_id=producto_id,
                almacen_id=almacen_id,
                costo_unitario=costo_unitario,
            )

        return self._normalizar_linea_conversion(
            indice=indice,
            linea=linea,
            producto=producto,
            producto_id=producto_id,
            almacen_id=almacen_id,
            costo_unitario=costo_unitario,
        )

    def _normalizar_linea_peso_variable(self, *, indice, linea, producto, producto_id, almacen_id, costo_unitario):
        metrica_base = getattr(producto, "metrica", None) or "kg"
        cantidad_cajas = _to_decimal(linea.get("cantidad_cajas") or linea.get("cantidad_original"))
        kilos_reales = _to_decimal(linea.get("kilos_reales") or linea.get("cantidad_convertida") or linea.get("cantidad"))

        if cantidad_cajas <= 0:
            raise ValueError(f"Línea {indice}: captura la cantidad de cajas para el producto de peso variable.")

        if kilos_reales <= 0:
            raise ValueError(f"Línea {indice}: captura los kilos reales para el producto de peso variable.")

        factor_conversion = (kilos_reales / cantidad_cajas) if cantidad_cajas > 0 else Decimal("0")
        equivalencia_texto = f"{_decimal_texto(cantidad_cajas)} cajas = {_decimal_texto(kilos_reales)} {metrica_base} reales"

        return {
            "producto_id": producto_id,
            "almacen_id": almacen_id,
            "cantidad": kilos_reales,
            "cantidad_original": cantidad_cajas,
            "conversion_id": None,
            "costo_unitario": costo_unitario,
            "conversion": None,
            "presentacion_nombre": "Caja peso variable",
            "presentacion_conversion_id": "peso_variable",
            "cantidad_presentacion": cantidad_cajas,
            "presentacion_factor_conversion": factor_conversion,
            "presentacion_metrica_default": metrica_base,
            "presentacion_equivalencia_texto": equivalencia_texto,
            "es_peso_variable": True,
            "cantidad_cajas": cantidad_cajas,
            "kilos_reales": kilos_reales,
            "costo_total": kilos_reales * costo_unitario,
        }

    def _normalizar_linea_conversion(self, *, indice, linea, producto, producto_id, almacen_id, costo_unitario):
        cantidad_input = _to_decimal(linea.get("cantidad"))
        if cantidad_input <= 0:
            raise ValueError(f"Línea {indice}: la cantidad debe ser mayor a 0.")

        try:
            captura = normalizar_captura_entrada(
                producto=producto,
                cantidad_capturada=cantidad_input,
                conversion_id_raw=linea.get("conversion_id"),
            )
        except ValueError as exc:
            raise ValueError(f"Línea {indice}: {exc}") from exc

        return {
            "producto_id": producto_id,
            "almacen_id": almacen_id,
            "cantidad": captura["cantidad_base"],
            "cantidad_original": cantidad_input,
            "conversion_id": captura["conversion_id"],
            "costo_unitario": costo_unitario,
            "conversion": captura["conversion"],
            "presentacion_nombre": captura["presentacion_nombre"],
            "presentacion_conversion_id": captura["presentacion_conversion_id"],
            "cantidad_presentacion": captura["cantidad_presentacion"],
            "presentacion_factor_conversion": captura["presentacion_factor_conversion"],
            "presentacion_metrica_default": captura["presentacion_metrica_default"],
            "presentacion_equivalencia_texto": captura["presentacion_equivalencia_texto"],
            "es_peso_variable": False,
            "cantidad_cajas": Decimal("0"),
            "kilos_reales": Decimal("0"),
            "costo_total": captura["cantidad_base"] * costo_unitario,
        }
