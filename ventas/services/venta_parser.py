from catalogos.models import Producto
from inventarios.utils import decimal_or_default as _to_decimal


class VentaPostParser:

    def __init__(self, formset, almacenes_permitidos, post_data=None, request=None):
        # `request` se conserva como compatibilidad temporal. La capa de vista
        # debe preferir enviar `post_data` para no acoplar el parser al request.
        self.post_data = post_data if post_data is not None else getattr(request, "POST", None)
        self.formset = formset
        self.almacenes_permitidos = almacenes_permitidos

    def parse(self):
        if self.post_data is None:
            return self._resultado(error="No fue posible interpretar la información enviada de la venta.")

        detalles = self.formset.save(commit=False)
        detalles_validos, error = self._get_detalles_validos(detalles)

        if error:
            return self._resultado(error=error)

        detalles_meta = self._parse_detalles_presentacion()

        if len(detalles_meta) != len(detalles_validos):
            return self._resultado(
                detalles_validos=detalles_validos,
                detalles_meta=detalles_meta,
                error="No fue posible interpretar las presentaciones de los productos capturados.",
            )

        productos_permitidos = {
            str(producto.id): producto
            for producto in Producto.objects.filter(
                id__in=[detalle.producto_id for detalle in detalles_validos]
            )
        }

        lineas_stock, error = self._parse_lineas_venta(
            productos_permitidos=productos_permitidos,
            almacenes_permitidos=self.almacenes_permitidos,
        )

        if error:
            return self._resultado(
                detalles_validos=detalles_validos,
                detalles_meta=detalles_meta,
                error=error,
            )

        return self._resultado(
            detalles_validos=detalles_validos,
            detalles_meta=detalles_meta,
            lineas_stock=lineas_stock,
        )

    def _get_detalles_validos(self, detalles):
        detalles_validos = []

        for detalle in detalles:
            if getattr(detalle, "DELETE", False):
                continue

            if not detalle.producto_id:
                continue

            if detalle.cantidad is None or detalle.cantidad <= 0:
                return [], "Hay renglones con cantidad inválida (<= 0)."

            detalles_validos.append(detalle)

        if not detalles_validos:
            return [], "Agrega al menos un producto a la venta."

        return detalles_validos, None

    def _parse_detalles_presentacion(self):
        producto_ids = self.post_data.getlist("detalle_producto_id")
        presentacion_ids = self.post_data.getlist("detalle_presentacion_id")
        cantidades_presentacion = self.post_data.getlist("detalle_cantidad_presentacion")
        factores = self.post_data.getlist("detalle_factor_conversion")
        presentaciones = self.post_data.getlist("detalle_presentacion_nombre")
        metricas_default = self.post_data.getlist("detalle_metrica_default")
        equivalencias = self.post_data.getlist("detalle_equivalencia_texto")

        detalles_meta = []
        total = len(producto_ids)

        for idx in range(total):
            cantidad_presentacion = _to_decimal(
                cantidades_presentacion[idx] if idx < len(cantidades_presentacion) else None,
                default=None,
            )

            factor = _to_decimal(
                factores[idx] if idx < len(factores) else None,
                default=None,
            )

            detalles_meta.append({
                "producto_id": (
                    producto_ids[idx] if idx < len(producto_ids) else ""
                ).strip(),
                "presentacion_id": (
                    presentacion_ids[idx] if idx < len(presentacion_ids) else ""
                ).strip() or "default",
                "cantidad_presentacion": cantidad_presentacion,
                "factor_conversion": factor,
                "presentacion_nombre": (
                    presentaciones[idx] if idx < len(presentaciones) else ""
                ).strip() or "Kilos",
                "metrica_default": (
                    metricas_default[idx] if idx < len(metricas_default) else ""
                ).strip() or "kg",
                "equivalencia_texto": (
                    equivalencias[idx] if idx < len(equivalencias) else ""
                ).strip(),
            })

        return detalles_meta

    def _parse_lineas_venta(self, productos_permitidos, almacenes_permitidos):
        producto_ids = self.post_data.getlist("linea_producto_id")
        almacen_ids = self.post_data.getlist("linea_almacen_id")
        cantidades = self.post_data.getlist("linea_cantidad")
        item_indexes = self.post_data.getlist("linea_item_index")

        if not (len(producto_ids) == len(almacen_ids) == len(cantidades)):
            return None, "No fue posible interpretar las asignaciones de almacén de la venta."

        lineas = []

        for idx, (raw_pid, raw_aid, raw_qty) in enumerate(
            zip(producto_ids, almacen_ids, cantidades)
        ):
            producto_id = (raw_pid or "").strip()
            almacen_id = (raw_aid or "").strip()
            cantidad = _to_decimal(raw_qty, default=None)

            item_index_raw = (
                item_indexes[idx] if idx < len(item_indexes) else ""
            ).strip()
            item_index = int(item_index_raw) if item_index_raw.isdigit() else None

            if not producto_id or not almacen_id:
                return None, "Hay asignaciones de almacén incompletas en el detalle."

            producto = productos_permitidos.get(producto_id)
            almacen = almacenes_permitidos.get(almacen_id)

            if not producto:
                return None, "Uno de los productos seleccionados ya no es válido."

            if not almacen:
                return None, "Uno de los almacenes seleccionados ya no es válido."

            if cantidad is None or cantidad <= 0:
                return None, f"La cantidad asignada para {producto} debe ser mayor a 0."

            lineas.append({
                "producto": producto,
                "almacen": almacen,
                "cantidad": cantidad,
                "item_index": item_index,
            })

        if not lineas:
            return None, "Agrega al menos un producto a la venta."

        return lineas, None

    def _resultado(
        self,
        detalles_validos=None,
        detalles_meta=None,
        lineas_stock=None,
        error=None,
    ):
        return {
            "detalles_validos": detalles_validos or [],
            "detalles_meta": detalles_meta or [],
            "lineas_stock": lineas_stock or [],
            "errores": [error] if error else [],
        }