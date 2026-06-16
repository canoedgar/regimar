from decimal import Decimal

from catalogos.models import ClienteProductoPrecio, Producto
from catalogos.services.clientes_precios import registrar_ultimo_precio_cliente
from inventarios.models import SalidaInventarioDetalle, SalidaInventarioDetalleAlmacen
from inventarios.services.stock import aplicar_movimientos_salida
from inventarios.services.venta_parser import VentaPostParser
from inventarios.services.ventas import VentaService
from django.utils import timezone


def marcar_nota_editada(salida, user=None):
    salida.editada_en = timezone.now()
    salida.editada_por = user if getattr(user, "is_authenticated", False) else None
    salida.save(update_fields=["editada_en", "editada_por"])


class EditarDatosNotaService:
    def __init__(self, *, form, user=None):
        self.form = form
        self.user = user

    def execute(self):
        salida = self.form.save(commit=False)
        salida.editada_en = timezone.now()
        salida.editada_por = self.user if getattr(self.user, "is_authenticated", False) else None
        salida.save()
        return salida


class AjustarPreciosNotaService:
    def __init__(self, *, formset, salida, user=None):
        self.formset = formset
        self.salida = salida
        self.user = user

    def validar(self):
        """
        Valida que el ajuste de precios respete el precio mínimo del producto.

        Regla:
        - El importe de la nota se calcula con cantidad KG/base × precio KG/base.
        - El precio capturado no puede quedar por debajo del precio mínimo autorizado.
        - Se permite solo cuando ya existe un precio cliente-producto registrado con ese mismo precio,
          que es la regla que ya usa el flujo actual de venta para reconocer un precio autorizado.
        """
        errores = []
        cliente = getattr(self.salida, "cliente_ref", None)

        for form in self.formset.forms:
            if not hasattr(form, "cleaned_data") or not form.cleaned_data:
                continue

            detalle = form.instance
            producto = getattr(detalle, "producto", None)
            precio = form.cleaned_data.get("precio_unitario")

            if not producto or precio is None:
                continue

            precio_minimo = getattr(producto, "precio_minimo", Decimal("0")) or Decimal("0")
            if precio_minimo <= 0 or precio >= precio_minimo:
                continue

            precio_autorizado = None
            if cliente:
                precio_autorizado = ClienteProductoPrecio.objects.filter(
                    cliente=cliente,
                    producto=producto,
                    ultimo_precio=precio,
                ).first()

            if precio_autorizado:
                continue

            errores.append(
                f"{producto.nombre}: el precio capturado ${precio} "
                f"es menor al precio mínimo autorizado ${precio_minimo}."
            )

        return errores

    def execute(self):
        errores = self.validar()
        if errores:
            raise ValueError("; ".join(errores))

        detalles = self.formset.save()
        marcar_nota_editada(self.salida, self.user)
        cliente = getattr(self.salida, "cliente_ref", None)
        for detalle in detalles:
            registrar_ultimo_precio_cliente(
                cliente=cliente,
                producto=detalle.producto,
                precio=detalle.precio_unitario,
                usuario=self.user if getattr(self.user, "is_authenticated", False) else None,
                observaciones=f"Ajuste de precio en nota {self.salida.folio}",
            )
        return detalles


class AgregarProductosNotaService:
    def __init__(self, *, request, salida, formset, almacenes_permitidos):
        self.request = request
        self.salida = salida
        self.formset = formset
        self.almacenes_permitidos = almacenes_permitidos
        self.resultado_parseo = None

    def validar(self):
        if not self.formset.is_valid():
            return ["Revisa los productos capturados."]

        errores = []
        repetidos = self._productos_repetidos()
        if repetidos:
            errores.append(
                "No se pueden agregar productos que ya existen en la nota o están repetidos en esta edición: "
                + ", ".join(repetidos)
                + "."
            )
            return errores

        parser = VentaPostParser(
            request=self.request,
            formset=self.formset,
            almacenes_permitidos=self.almacenes_permitidos,
        )
        self.resultado_parseo = parser.parse()
        errores.extend(self.resultado_parseo["errores"])
        if errores:
            return errores

        dummy_form = type("NotaVentaDummyForm", (), {
            "cleaned_data": {"cliente_ref": self.salida.cliente_ref},
        })()
        venta_service = VentaService(
            form=dummy_form,
            detalles_validos=self.resultado_parseo["detalles_validos"],
            detalles_meta=self.resultado_parseo["detalles_meta"],
            lineas_stock=self.resultado_parseo["lineas_stock"],
            almacenes_permitidos=self.almacenes_permitidos,
            request=self.request,
        )
        errores.extend(venta_service.validar_stock())
        return errores

    def execute(self):
        if self.resultado_parseo is None:
            errores = self.validar()
            if errores:
                raise ValueError("; ".join(errores))

        detalles = self._guardar_productos()
        marcar_nota_editada(self.salida, self.request.user)
        return detalles

    def _productos_repetidos(self):
        productos_existentes = set(self.salida.detalles.values_list("producto_id", flat=True))
        vistos = set()
        repetidos = []
        try:
            total = int(self.request.POST.get("nuevos-TOTAL_FORMS", "0") or 0)
        except (TypeError, ValueError):
            total = 0

        for idx in range(total):
            raw_producto_id = (self.request.POST.get(f"nuevos-{idx}-producto") or "").strip()
            if not raw_producto_id.isdigit():
                continue
            producto_id = int(raw_producto_id)
            if producto_id in productos_existentes or producto_id in vistos:
                repetidos.append(producto_id)
            vistos.add(producto_id)

        if not repetidos:
            return []
        return list(
            Producto.objects.filter(id__in=set(repetidos)).order_by("nombre").values_list("nombre", flat=True)
        )

    def _agrupar_requeridos_por_almacen(self):
        requeridos = {}
        for linea in self.resultado_parseo["lineas_stock"]:
            almacen_id = linea["almacen"].id
            producto_id = linea["producto"].id
            requeridos.setdefault(almacen_id, {})
            requeridos[almacen_id][producto_id] = (
                requeridos[almacen_id].get(producto_id, Decimal("0")) + linea["cantidad"]
            )
        return requeridos

    def _primer_almacen_de_item(self, item_index):
        for linea in self.resultado_parseo["lineas_stock"]:
            if linea.get("item_index") == item_index:
                return linea["almacen"]
        lineas = self.resultado_parseo["lineas_stock"]
        return lineas[0]["almacen"] if lineas else self.salida.almacen

    def _guardar_productos(self):
        detalles_por_index = {}
        detalles_validos = self.resultado_parseo["detalles_validos"]
        detalles_meta = self.resultado_parseo["detalles_meta"]

        for index, detalle in enumerate(detalles_validos):
            meta = detalles_meta[index] if index < len(detalles_meta) else {}
            detalle.salida = self.salida
            detalle.almacen = self._primer_almacen_de_item(index)
            producto = getattr(detalle, "producto", None)
            detalle.costo_unitario_aplicado = (
                getattr(producto, "costo_promedio", Decimal("0")) if producto else Decimal("0")
            )
            detalle.presentacion_nombre = meta.get("presentacion_nombre") or "Kilos"
            detalle.presentacion_conversion_id = meta.get("presentacion_id") or "default"
            cantidad_presentacion = meta.get("cantidad_presentacion")
            detalle.cantidad_presentacion = (
                cantidad_presentacion
                if cantidad_presentacion is not None
                else detalle.cantidad
            )
            detalle.presentacion_factor_conversion = meta.get("factor_conversion") or Decimal("1")
            detalle.presentacion_metrica_default = meta.get("metrica_default") or "kg"
            detalle.presentacion_equivalencia_texto = (
                meta.get("equivalencia_texto")
                or f"1 {detalle.presentacion_nombre} = {detalle.presentacion_factor_conversion} {detalle.presentacion_metrica_default}"
            )
            detalle.save()
            detalles_por_index[index] = detalle

        for linea in self.resultado_parseo["lineas_stock"]:
            detalle = detalles_por_index.get(linea.get("item_index"))
            if not detalle:
                continue
            SalidaInventarioDetalleAlmacen.objects.create(
                detalle=detalle,
                almacen=linea["almacen"],
                cantidad=linea["cantidad"],
            )

        venta_service = VentaService(
            form=type("NotaVentaDummyForm", (), {"cleaned_data": {"cliente_ref": self.salida.cliente_ref}})(),
            detalles_validos=detalles_validos,
            detalles_meta=detalles_meta,
            lineas_stock=self.resultado_parseo["lineas_stock"],
            almacenes_permitidos=self.almacenes_permitidos,
            request=self.request,
        )

        requeridos_por_almacen = self._agrupar_requeridos_por_almacen()
        venta_service._registrar_entradas_virtuales(self.salida, requeridos_por_almacen)

        for almacen_id, requeridos in requeridos_por_almacen.items():
            aplicar_movimientos_salida(almacen_id=almacen_id, requeridos=requeridos)

        cliente = getattr(self.salida, "cliente_ref", None)
        for detalle in detalles_por_index.values():
            registrar_ultimo_precio_cliente(
                cliente=cliente,
                producto=detalle.producto,
                precio=detalle.precio_unitario,
                usuario=self.request.user if self.request.user.is_authenticated else None,
                observaciones=f"Producto agregado en nota {self.salida.folio}",
            )

        return list(detalles_por_index.values())
