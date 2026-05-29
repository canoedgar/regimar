from decimal import Decimal
from datetime import timedelta

from catalogos.models import Producto, ClienteProductoPrecio, PrecioMenorMinimoAutorizacion
from inventarios.models import SalidaInventarioDetalleAlmacen
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone
from catalogos.services.clientes_precios import registrar_ultimo_precio_cliente
from inventarios.services.stock import (
    validar_stock_suficiente,
    errores_stock_humano,
    aplicar_movimientos_salida,
)


class VentaService:
    def __init__(
        self,
        form,
        detalles_validos,
        detalles_meta,
        lineas_stock,
        almacenes_permitidos,
        request=None,
    ):
        self.form = form
        self.detalles_validos = detalles_validos
        self.detalles_meta = detalles_meta
        self.lineas_stock = lineas_stock
        self.almacenes_permitidos = almacenes_permitidos
        self.request = request

    def validar_stock(self):
        requeridos_por_almacen = self._agrupar_requeridos_por_almacen()

        productos = list(Producto.objects.filter(
            id__in=[detalle.producto_id for detalle in self.detalles_validos]
        ))
        productos_por_id = {producto.id: str(producto) for producto in productos}
        productos_obj_por_id = {producto.id: producto for producto in productos}

        errores = []

        errores.extend(self._validar_precios_minimos(productos_obj_por_id))

        for almacen_id, requeridos in requeridos_por_almacen.items():
            ok, disponibles, faltantes = validar_stock_suficiente(
                almacen_id=almacen_id,
                requeridos=requeridos,
            )

            if not ok:
                errores.extend(
                    errores_stock_humano(
                        almacen_nombre=str(self.almacenes_permitidos[str(almacen_id)]),
                        faltantes=faltantes,
                        disponibles=disponibles,
                        productos_por_id=productos_por_id,
                    )
                )

        return errores

    def guardar(self):
        requeridos_por_almacen = self._agrupar_requeridos_por_almacen()

        salida = self.form.save(commit=False)
        salida.almacen = self.lineas_stock[0]["almacen"]

        self._agregar_observacion_almacenes(salida)
        salida.save()

        detalles_por_index = self._guardar_detalles(salida)
        self._guardar_asignaciones(detalles_por_index)

        for almacen_id, requeridos in requeridos_por_almacen.items():
            aplicar_movimientos_salida(
                almacen_id=almacen_id,
                requeridos=requeridos,
            )

        cliente = getattr(salida, "cliente_ref", None)
        for detalle in detalles_por_index.values():
            registrar_ultimo_precio_cliente(
                cliente=cliente,
                producto=detalle.producto,
                precio=detalle.precio_unitario,
                usuario=self.request.user if self.request else None,
                observaciones=f"Venta {salida.folio}",
            )

        return salida

    def _validar_precios_minimos(self, productos_obj_por_id):
        errores = []
        cliente = self.form.cleaned_data.get("cliente_ref") if hasattr(self.form, "cleaned_data") else None

        for detalle in self.detalles_validos:
            producto = productos_obj_por_id.get(detalle.producto_id)
            if not producto:
                continue

            precio_minimo = getattr(producto, "precio_minimo", Decimal("0")) or Decimal("0")
            precio_unitario = detalle.precio_unitario or Decimal("0")

            if precio_minimo <= 0 or precio_unitario >= precio_minimo:
                continue

            # Si un administrador ya autorizó este precio para este cliente/producto, se permite la venta.
            precio_autorizado = None
            if cliente:
                precio_autorizado = ClienteProductoPrecio.objects.filter(
                    cliente=cliente,
                    producto=producto,
                    ultimo_precio=precio_unitario,
                ).first()

            if precio_autorizado:
                continue

            envio_confirmado = (
                self.request
                and self.request.POST.get("confirmar_envio_autorizacion_precio") == "1"
            )

            token = None
            if envio_confirmado:
                token = self._crear_autorizacion_precio_minimo(
                    cliente=cliente,
                    producto=producto,
                    precio_actual=getattr(producto, "precio", Decimal("0")) or Decimal("0"),
                    precio_minimo=precio_minimo,
                    precio_solicitado=precio_unitario,
                )

            extra = ""
            if token:
                extra = " Se envió solicitud de autorización a administradores activos."
            elif not envio_confirmado:
                extra = " Confirma el envío de la solicitud de autorización antes de continuar."

            errores.append(
                f"{producto.nombre}: el precio solicitado ${precio_unitario} "
                f"es menor al mínimo autorizado ${precio_minimo}.{extra}"
            )

        return errores

    def _crear_autorizacion_precio_minimo(self, *, cliente, producto, precio_actual, precio_minimo, precio_solicitado):
        if not cliente or not self.request:
            return None

        autorizacion = PrecioMenorMinimoAutorizacion.objects.create(
            cliente=cliente,
            producto=producto,
            usuario_solicita=self.request.user if self.request.user.is_authenticated else None,
            precio_actual=precio_actual,
            precio_minimo=precio_minimo,
            precio_solicitado=precio_solicitado,
            expira_en=timezone.now() + timedelta(hours=24),
        )

        User = get_user_model()
        admins = User.objects.filter(is_active=True).filter(is_superuser=True)
        correos = [u.email for u in admins if u.email]
        if not correos:
            return autorizacion

        url = self.request.build_absolute_uri(
            reverse("autorizar_precio_minimo", kwargs={"token": autorizacion.token})
        )
        usuario = self.request.user.get_username() if self.request.user.is_authenticated else "Sistema"
        asunto = f"Autorización de precio menor al mínimo - {producto.nombre}"
        cuerpo = (
            f"Cliente: {cliente}\n"
            f"Producto: {producto.nombre}\n"
            f"Precio actual/sugerido: ${precio_actual}\n"
            f"Precio mínimo: ${precio_minimo}\n"
            f"Precio solicitado: ${precio_solicitado}\n"
            f"Usuario: {usuario}\n"
            f"Fecha: {timezone.localtime().strftime('%Y-%m-%d %H:%M')}\n\n"
            f"Autorizar: {url}\n"
            "Este enlace es de un solo uso y expira en 24 horas."
        )
        send_mail(
            asunto,
            cuerpo,
            getattr(settings, "DEFAULT_FROM_EMAIL", None),
            correos,
            fail_silently=True,
        )
        return autorizacion

    def _agrupar_requeridos_por_almacen(self):
        requeridos = {}

        for linea in self.lineas_stock:
            almacen_id = linea["almacen"].id
            producto_id = linea["producto"].id

            requeridos.setdefault(almacen_id, {})
            requeridos[almacen_id][producto_id] = (
                requeridos[almacen_id].get(producto_id, Decimal("0"))
                + linea["cantidad"]
            )

        return requeridos

    def _agregar_observacion_almacenes(self, salida):
        almacenes_usados = []
        vistos = set()

        for linea in self.lineas_stock:
            almacen = linea["almacen"]
            key = str(almacen.id)

            if key not in vistos:
                vistos.add(key)
                almacenes_usados.append(str(almacen))

        if len(almacenes_usados) <= 1:
            return

        nota_almacenes = "Almacenes surtidos: " + ", ".join(almacenes_usados)
        observaciones = (salida.observaciones or "").strip()

        salida.observaciones = (
            observaciones + "\n" + nota_almacenes
            if observaciones
            else nota_almacenes
        )

    def _guardar_detalles(self, salida):
        detalles_por_index = {}

        for index, detalle in enumerate(self.detalles_validos):
            meta = self.detalles_meta[index] if index < len(self.detalles_meta) else {}

            detalle.salida = salida
            detalle.almacen = salida.almacen

            producto = getattr(detalle, "producto", None)
            detalle.costo_unitario_aplicado = (
                getattr(producto, "costo_promedio", Decimal("0"))
                if producto else Decimal("0")
            )

            detalle.presentacion_nombre = (
                meta.get("presentacion_nombre")
                or getattr(detalle, "presentacion_nombre", "")
                or "Kilos"
            )
            detalle.presentacion_conversion_id = (
                meta.get("presentacion_id")
                or "default"
            )
            cantidad_presentacion = meta.get("cantidad_presentacion")
            detalle.cantidad_presentacion = (
                cantidad_presentacion
                if cantidad_presentacion is not None
                else detalle.cantidad
            )
            detalle.presentacion_factor_conversion = (
                meta.get("factor_conversion")
                or Decimal("1")
            )
            detalle.presentacion_metrica_default = (
                meta.get("metrica_default")
                or "kg"
            )
            detalle.presentacion_equivalencia_texto = (
                meta.get("equivalencia_texto")
                or f"1 {detalle.presentacion_nombre} = "
                   f"{detalle.presentacion_factor_conversion} "
                   f"{detalle.presentacion_metrica_default}"
            )

            detalle.save()
            detalles_por_index[index] = detalle

        return detalles_por_index

    def _guardar_asignaciones(self, detalles_por_index):
        for linea in self.lineas_stock:
            detalle = detalles_por_index.get(linea.get("item_index"))

            if not detalle:
                continue

            SalidaInventarioDetalleAlmacen.objects.create(
                detalle=detalle,
                almacen=linea["almacen"],
                cantidad=linea["cantidad"],
            )