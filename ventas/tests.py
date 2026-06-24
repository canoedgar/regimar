from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.http import QueryDict
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalogos.models import (
    Almacen,
    Cliente,
    ClienteProductoPrecio,
    PrecioMenorMinimoAutorizacion,
    Producto,
    ProductoMetricaConversion,
)
from inventarios.models import (
    EntradaInventario,
    InventarioStock,
    SalidaInventario,
    SalidaInventarioDetalle,
    SalidaInventarioDetalleAlmacen,
)
from inventarios.services.costos import aplicar_entrada_con_costo
from ventas.forms import SalidaVentaForm
from ventas.models import NotaVenta, NotaVentaDetalle
from ventas.selectors.ventas import build_productos_ui
from ventas.services.venta_credito import VentaCreditoService
from ventas.services.venta_data import VentaOperacionData, VentaRequestContext
from ventas.services.venta_parser import VentaPostParser
from ventas.services.venta_precio import VentaPrecioMinimoService
from ventas.services.ventas import VentaService, es_almacen_venta_virtual


D = Decimal


class VentasFactoryMixin:
    """Objetos mínimos para probar el módulo de ventas sin depender de vistas."""

    def crear_producto(self, nombre="Producto venta prueba", **kwargs):
        defaults = {
            "nombre": nombre,
            "metrica": "kg",
            "precio": D("100.00"),
            "precio_minimo": D("0.00"),
            "ultimo_costo_compra": D("0.00"),
            "costo_promedio": D("0.00"),
            "stock": D("0.00"),
        }
        defaults.update(kwargs)
        return Producto.objects.create(**defaults)

    def crear_cliente(self, nombre="Cliente venta prueba", **kwargs):
        defaults = {
            "nombre_fiscal": nombre,
            "nombre_comercial": nombre,
        }
        defaults.update(kwargs)
        return Cliente.objects.create(**defaults)

    def crear_almacen(self, codigo="VTA", nombre="Almacén venta", **kwargs):
        defaults = {
            "codigo": codigo,
            "nombre": nombre,
            "tipo": "FISICO",
            "permite_ventas": True,
            "permite_transferencias": True,
            "es_activo": True,
        }
        defaults.update(kwargs)
        return Almacen.objects.create(**defaults)

    def crear_almacen_virtual(self, codigo="VIRT", nombre="Almacén virtual", **kwargs):
        defaults = {
            "tipo": "VIRTUAL",
            "es_virtual_sistema": True,
            "permite_ventas": True,
            "permite_transferencias": False,
            "es_activo": True,
        }
        defaults.update(kwargs)
        return self.crear_almacen(codigo=codigo, nombre=nombre, **defaults)

    def crear_detalle_venta(self, *, producto, cantidad="1.00", precio="100.00"):
        return SalidaInventarioDetalle(
            producto=producto,
            cantidad=D(cantidad),
            precio_unitario=D(precio),
        )

    def crear_salida_venta(self, *, folio="VTA-TEST-001", cliente=None, persistida=False, **kwargs):
        defaults = {
            "folio": folio,
            "fecha": timezone.localdate(),
            "tipo": SalidaInventario.TIPO_VENTA,
            "cliente_ref": cliente,
            "cliente": str(cliente or "Cliente mostrador"),
            "forma_pago_venta": SalidaInventario.FORMA_PAGO_CONTADO,
            "estado_pago": SalidaInventario.ESTADO_PAGO_PAGADO,
            "logo_nota": SalidaInventario.LOGO_CPC_ALIMENTOS,
        }
        defaults.update(kwargs)
        salida = SalidaInventario(**defaults)
        if persistida:
            salida.save()
        return salida

    def crear_venta_service(self, *, salida, detalle, almacen, cliente=None, validar_credito=False):
        data = VentaOperacionData(
            salida=salida,
            cliente=cliente or getattr(salida, "cliente_ref", None),
            fecha=salida.fecha,
            contexto=VentaRequestContext(usuario=None),
            validar_credito=validar_credito,
        )
        return VentaService(
            data=data,
            detalles_validos=[detalle],
            detalles_meta=[{}],
            lineas_stock=[
                {
                    "almacen": almacen,
                    "producto": detalle.producto,
                    "cantidad": detalle.cantidad,
                    "item_index": 0,
                }
            ],
            almacenes_permitidos={str(almacen.id): almacen},
        )


class VentaModelProxyTests(VentasFactoryMixin, TestCase):
    def test_nota_venta_proxy_usa_tabla_de_salida_inventario(self):
        nota = NotaVenta.objects.create(
            folio="VTA-PROXY-001",
            fecha=timezone.localdate(),
            tipo=SalidaInventario.TIPO_VENTA,
            cliente="Cliente proxy",
        )

        self.assertEqual(nota.tipo, SalidaInventario.TIPO_VENTA)
        self.assertTrue(NotaVenta._meta.proxy)
        self.assertEqual(SalidaInventario.objects.filter(pk=nota.pk).count(), 1)

    def test_nota_venta_detalle_proxy_usa_detalle_de_salida(self):
        producto = self.crear_producto(nombre="Producto proxy")
        nota = self.crear_salida_venta(folio="VTA-PROXY-002", persistida=True)

        detalle = NotaVentaDetalle.objects.create(
            salida=nota,
            producto=producto,
            cantidad=D("2.00"),
            precio_unitario=D("150.00"),
        )

        self.assertTrue(NotaVentaDetalle._meta.proxy)
        self.assertEqual(SalidaInventarioDetalle.objects.filter(pk=detalle.pk).count(), 1)
        self.assertEqual(nota.detalles.count(), 1)


class VentaUrlsTests(TestCase):
    def test_urls_principales_de_ventas_resuelven(self):
        self.assertEqual(reverse("ventas_list"), "/ventas/")
        self.assertEqual(reverse("salida_venta_create"), "/ventas/nueva/")
        self.assertEqual(reverse("precios_cliente_api"), "/ventas/precios-cliente/")


class SalidaVentaFormTests(VentasFactoryMixin, TestCase):
    def test_formulario_de_venta_valido_guarda_tipo_venta(self):
        cliente = self.crear_cliente(nombre="Cliente form venta")
        data = {
            "folio": "VTA-FORM-001",
            "fecha": timezone.localdate().isoformat(),
            "cliente_ref": str(cliente.id),
            "forma_pago_venta": SalidaInventario.FORMA_PAGO_CONTADO,
            "estado_pago": SalidaInventario.ESTADO_PAGO_PAGADO,
            "cliente": "Cliente form venta",
            "cliente_direccion": "Dirección de prueba",
            "cliente_contacto": "Contacto",
            "logo_nota": SalidaInventario.LOGO_CPC_ALIMENTOS,
            "documento_referencia": "REM-001",
            "motivo": "",
            "observaciones": "",
        }

        form = SalidaVentaForm(data=data)

        self.assertTrue(form.is_valid(), form.errors)
        salida = form.save(commit=False)
        self.assertEqual(salida.tipo, SalidaInventario.TIPO_VENTA)
        self.assertIsNone(salida.proyecto)

    def test_formulario_de_venta_requiere_cliente_forma_pago_estado_y_logo(self):
        form = SalidaVentaForm(data={"folio": "VTA-FORM-002", "fecha": timezone.localdate().isoformat()})

        self.assertFalse(form.is_valid())
        self.assertIn("cliente_ref", form.errors)
        self.assertIn("forma_pago_venta", form.errors)
        self.assertIn("estado_pago", form.errors)
        self.assertIn("logo_nota", form.errors)


class VentaRequestContextTests(TestCase):
    def test_from_request_extrae_usuario_autenticado_confirmacion_y_url_builder(self):
        post = QueryDict("", mutable=True)
        post.update({"confirmar_envio_autorizacion_precio": "1"})
        usuario = SimpleNamespace(
            is_authenticated=True,
            get_username=lambda: "usuario.prueba",
        )
        request = SimpleNamespace(
            user=usuario,
            POST=post,
            build_absolute_uri=lambda path: f"https://portal.test{path}",
        )

        contexto = VentaRequestContext.from_request(request)

        self.assertIs(contexto.usuario, usuario)
        self.assertIs(contexto.credito_request, request)
        self.assertTrue(contexto.confirmar_envio_autorizacion_precio)
        self.assertEqual(contexto.username(), "usuario.prueba")
        self.assertEqual(contexto.build_absolute_uri("/ventas/"), "https://portal.test/ventas/")

    def test_from_request_sin_request_regresa_contexto_seguro(self):
        contexto = VentaRequestContext.from_request(None)

        self.assertIsNone(contexto.usuario)
        self.assertIsNone(contexto.credito_request)
        self.assertFalse(contexto.confirmar_envio_autorizacion_precio)
        self.assertEqual(contexto.username(), "Sistema")
        self.assertEqual(contexto.build_absolute_uri("/ventas/"), "/ventas/")


class VentaPostParserTests(VentasFactoryMixin, TestCase):
    class FormsetFake:
        def __init__(self, detalles):
            self.detalles = detalles

        def save(self, commit=False):
            return self.detalles

    def _post_base(self, *, producto, almacen, cantidad="3.00"):
        post = QueryDict("", mutable=True)
        post.setlist("detalle_producto_id", [str(producto.id)])
        post.setlist("detalle_presentacion_id", ["default"])
        post.setlist("detalle_cantidad_presentacion", [cantidad])
        post.setlist("detalle_factor_conversion", ["1"])
        post.setlist("detalle_presentacion_nombre", ["Kilos"])
        post.setlist("detalle_metrica_default", ["kg"])
        post.setlist("detalle_equivalencia_texto", ["1 Kilos = 1 kg"])
        post.setlist("linea_producto_id", [str(producto.id)])
        post.setlist("linea_almacen_id", [str(almacen.id)])
        post.setlist("linea_cantidad", [cantidad])
        post.setlist("linea_item_index", ["0"])
        return post

    def test_parser_interpreta_detalles_presentacion_y_lineas_stock(self):
        producto = self.crear_producto(nombre="Producto parser")
        almacen = self.crear_almacen(codigo="PAR", nombre="Almacén parser")
        detalle = self.crear_detalle_venta(producto=producto, cantidad="3.00")
        post = self._post_base(producto=producto, almacen=almacen, cantidad="3.00")

        resultado = VentaPostParser(
            post_data=post,
            formset=self.FormsetFake([detalle]),
            almacenes_permitidos={str(almacen.id): almacen},
        ).parse()

        self.assertEqual(resultado["errores"], [])
        self.assertEqual(resultado["detalles_validos"], [detalle])
        self.assertEqual(resultado["detalles_meta"][0]["presentacion_id"], "default")
        self.assertEqual(resultado["detalles_meta"][0]["cantidad_presentacion"], D("3.00"))
        self.assertEqual(resultado["lineas_stock"][0]["producto"], producto)
        self.assertEqual(resultado["lineas_stock"][0]["almacen"], almacen)
        self.assertEqual(resultado["lineas_stock"][0]["cantidad"], D("3.00"))

    def test_parser_rechaza_cantidad_de_detalle_invalida(self):
        producto = self.crear_producto(nombre="Producto parser inválido")
        almacen = self.crear_almacen(codigo="PINV", nombre="Almacén parser inválido")
        detalle = self.crear_detalle_venta(producto=producto, cantidad="0.00")
        post = self._post_base(producto=producto, almacen=almacen, cantidad="0.00")

        resultado = VentaPostParser(
            post_data=post,
            formset=self.FormsetFake([detalle]),
            almacenes_permitidos={str(almacen.id): almacen},
        ).parse()

        self.assertEqual(resultado["errores"], ["Hay renglones con cantidad inválida (<= 0)."])
        self.assertEqual(resultado["lineas_stock"], [])

    def test_parser_rechaza_almacen_no_permitido(self):
        producto = self.crear_producto(nombre="Producto parser almacén")
        almacen = self.crear_almacen(codigo="PNO", nombre="Almacén no permitido")
        detalle = self.crear_detalle_venta(producto=producto, cantidad="1.00")
        post = self._post_base(producto=producto, almacen=almacen, cantidad="1.00")

        resultado = VentaPostParser(
            post_data=post,
            formset=self.FormsetFake([detalle]),
            almacenes_permitidos={},
        ).parse()

        self.assertEqual(resultado["errores"], ["Uno de los almacenes seleccionados ya no es válido."])


class VentaSelectorTests(VentasFactoryMixin, TestCase):
    def test_build_productos_ui_incluye_almacen_virtual_sin_stock_previo(self):
        producto = self.crear_producto(nombre="Producto UI virtual")
        almacen_virtual = self.crear_almacen_virtual(codigo="UIV", nombre="Virtual UI")
        ProductoMetricaConversion.objects.create(
            producto=producto,
            nombre="Caja 10 kg",
            unidad_origen="Caja",
            cantidad_origen=D("1.00"),
            factor_conversion=D("10.00"),
            activo=True,
        )

        productos_ui = build_productos_ui()
        producto_ui = next(item for item in productos_ui if item["id"] == str(producto.id))

        almacenes_ids = {item["id"] for item in producto_ui["almacenes"]}
        self.assertIn(str(almacen_virtual.id), almacenes_ids)
        self.assertTrue(any(conv["id"] != "default" for conv in producto_ui["conversiones"]))


class VentaServiceTests(VentasFactoryMixin, TestCase):
    def test_es_almacen_venta_virtual_detecta_virtual_por_tipo_o_flag(self):
        fisico = self.crear_almacen(codigo="FIS", nombre="Físico")
        virtual_tipo = self.crear_almacen(codigo="VTI", nombre="Virtual tipo", tipo="VIRTUAL")
        virtual_flag = self.crear_almacen(
            codigo="VFL",
            nombre="Virtual flag",
            tipo="FISICO",
            es_virtual_sistema=True,
        )

        self.assertFalse(es_almacen_venta_virtual(fisico))
        self.assertTrue(es_almacen_venta_virtual(virtual_tipo))
        self.assertTrue(es_almacen_venta_virtual(virtual_flag))

    def test_venta_fisica_valida_y_descuenta_stock(self):
        producto = self.crear_producto(nombre="Producto venta física", costo_promedio=D("20.00"))
        almacen = self.crear_almacen(codigo="VFIS", nombre="Ventas físico")
        aplicar_entrada_con_costo(
            producto_id=producto.id,
            almacen_id=almacen.id,
            cantidad=D("10.00"),
            costo_unitario=D("20.00"),
        )
        salida = self.crear_salida_venta(folio="VTA-SVC-001")
        detalle = self.crear_detalle_venta(producto=producto, cantidad="3.00", precio="100.00")
        service = self.crear_venta_service(salida=salida, detalle=detalle, almacen=almacen)

        self.assertEqual(service.validar_stock(), [])
        venta = service.guardar()

        stock = InventarioStock.objects.get(producto=producto, almacen=almacen)
        producto.refresh_from_db()

        self.assertEqual(venta.detalles.count(), 1)
        self.assertEqual(SalidaInventarioDetalleAlmacen.objects.count(), 1)
        self.assertEqual(stock.cantidad, D("7.00"))
        self.assertEqual(producto.stock, D("7.00"))

    def test_venta_fisica_reporta_stock_insuficiente(self):
        producto = self.crear_producto(nombre="Producto venta sin stock")
        almacen = self.crear_almacen(codigo="VSIN", nombre="Ventas sin stock")
        salida = self.crear_salida_venta(folio="VTA-SVC-002")
        detalle = self.crear_detalle_venta(producto=producto, cantidad="1.00", precio="100.00")
        service = self.crear_venta_service(salida=salida, detalle=detalle, almacen=almacen)

        errores = service.validar_stock()

        self.assertEqual(len(errores), 1)
        self.assertIn("Stock insuficiente", errores[0])

    def test_venta_virtual_genera_entrada_y_salida_sin_dejar_stock_negativo(self):
        producto = self.crear_producto(
            nombre="Producto venta virtual",
            ultimo_costo_compra=D("12.00"),
            costo_promedio=D("12.00"),
        )
        almacen_virtual = self.crear_almacen_virtual(codigo="VVIR", nombre="Ventas virtual")
        salida = self.crear_salida_venta(folio="VTA-VIRT-001")
        detalle = self.crear_detalle_venta(producto=producto, cantidad="5.00", precio="100.00")
        service = self.crear_venta_service(salida=salida, detalle=detalle, almacen=almacen_virtual)

        self.assertEqual(service.validar_stock(), [])
        venta = service.guardar()

        entrada_virtual = EntradaInventario.objects.get(documento_referencia=venta.folio)
        stock = InventarioStock.objects.get(producto=producto, almacen=almacen_virtual)
        producto.refresh_from_db()

        self.assertEqual(entrada_virtual.tipo, EntradaInventario.TIPO_AJUSTE_POSITIVO)
        self.assertEqual(entrada_virtual.detalles.get().cantidad, D("5.00"))
        self.assertEqual(venta.detalles.get().cantidad, D("5.00"))
        self.assertEqual(stock.cantidad, D("0.00"))
        self.assertEqual(producto.stock, D("0.00"))

    def test_venta_con_multiples_almacenes_agrega_observacion(self):
        producto = self.crear_producto(nombre="Producto multi almacén", costo_promedio=D("15.00"))
        almacen_1 = self.crear_almacen(codigo="MUL1", nombre="Múltiple 1")
        almacen_2 = self.crear_almacen(codigo="MUL2", nombre="Múltiple 2")
        aplicar_entrada_con_costo(producto_id=producto.id, almacen_id=almacen_1.id, cantidad=D("2.00"), costo_unitario=D("15.00"))
        aplicar_entrada_con_costo(producto_id=producto.id, almacen_id=almacen_2.id, cantidad=D("2.00"), costo_unitario=D("15.00"))
        salida = self.crear_salida_venta(folio="VTA-MUL-001", observaciones="Observación original")
        detalle = self.crear_detalle_venta(producto=producto, cantidad="4.00", precio="100.00")
        data = VentaOperacionData(
            salida=salida,
            fecha=salida.fecha,
            contexto=VentaRequestContext(usuario=None),
            validar_credito=False,
        )
        service = VentaService(
            data=data,
            detalles_validos=[detalle],
            detalles_meta=[{}],
            lineas_stock=[
                {"almacen": almacen_1, "producto": producto, "cantidad": D("2.00"), "item_index": 0},
                {"almacen": almacen_2, "producto": producto, "cantidad": D("2.00"), "item_index": 0},
            ],
            almacenes_permitidos={str(almacen_1.id): almacen_1, str(almacen_2.id): almacen_2},
        )

        self.assertEqual(service.validar_stock(), [])
        venta = service.guardar()

        self.assertIn("Observación original", venta.observaciones)
        self.assertIn("Almacenes surtidos", venta.observaciones)
        self.assertEqual(SalidaInventarioDetalleAlmacen.objects.count(), 2)


class VentaPrecioMinimoServiceTests(VentasFactoryMixin, TestCase):
    def setUp(self):
        self.cliente = self.crear_cliente(nombre="Cliente precio mínimo")
        self.producto = self.crear_producto(
            nombre="Producto precio mínimo ventas",
            precio=D("100.00"),
            precio_minimo=D("80.00"),
        )
        self.detalle = self.crear_detalle_venta(
            producto=self.producto,
            cantidad="1.00",
            precio="70.00",
        )

    def test_precio_menor_minimo_sin_confirmacion_no_crea_autorizacion(self):
        notificador = Mock()
        contexto = VentaRequestContext(confirmar_envio_autorizacion_precio=False)
        service = VentaPrecioMinimoService(
            cliente=self.cliente,
            contexto=contexto,
            notificador=notificador,
        )

        errores = service.validar_detalles(
            detalles_validos=[self.detalle],
            productos_por_id={self.producto.id: self.producto},
        )

        self.assertEqual(len(errores), 1)
        self.assertIn("Confirma el envío", errores[0])
        self.assertEqual(PrecioMenorMinimoAutorizacion.objects.count(), 0)
        notificador.enviar_solicitud.assert_not_called()

    def test_precio_menor_minimo_con_confirmacion_crea_autorizacion_y_notifica(self):
        notificador = Mock()
        contexto = VentaRequestContext(confirmar_envio_autorizacion_precio=True)
        service = VentaPrecioMinimoService(
            cliente=self.cliente,
            contexto=contexto,
            notificador=notificador,
        )

        errores = service.validar_detalles(
            detalles_validos=[self.detalle],
            productos_por_id={self.producto.id: self.producto},
        )

        autorizacion = PrecioMenorMinimoAutorizacion.objects.get()
        self.assertEqual(len(errores), 1)
        self.assertIn("Se envió solicitud", errores[0])
        self.assertEqual(autorizacion.cliente, self.cliente)
        self.assertEqual(autorizacion.producto, self.producto)
        self.assertEqual(autorizacion.precio_solicitado, D("70.00"))
        notificador.enviar_solicitud.assert_called_once_with(
            autorizacion=autorizacion,
            contexto=contexto,
        )

    def test_precio_cliente_ya_autorizado_no_genera_error(self):
        ClienteProductoPrecio.objects.create(
            cliente=self.cliente,
            producto=self.producto,
            ultimo_precio=D("70.00"),
        )
        service = VentaPrecioMinimoService(cliente=self.cliente)

        errores = service.validar_detalles(
            detalles_validos=[self.detalle],
            productos_por_id={self.producto.id: self.producto},
        )

        self.assertEqual(errores, [])
        self.assertEqual(PrecioMenorMinimoAutorizacion.objects.count(), 0)


class VentaCreditoServiceTests(VentasFactoryMixin, TestCase):
    def test_validar_delega_en_servicio_de_credito_y_guarda_autorizacion(self):
        cliente = self.crear_cliente(nombre="Cliente crédito ventas", limite_credito=D("100.00"))
        contexto = VentaRequestContext(credito_request=SimpleNamespace(user=None))
        autorizacion = SimpleNamespace(pk=1)

        with patch("ventas.services.venta_credito.validar_credito_cliente_para_venta") as mock_validar:
            mock_validar.return_value = (["requiere autorización"], autorizacion)
            service = VentaCreditoService(
                cliente=cliente,
                fecha_venta=date(2026, 1, 1),
                contexto=contexto,
                total_venta_override=D("150.00"),
            )

            errores = service.validar()

        self.assertEqual(errores, ["requiere autorización"])
        self.assertIs(service.autorizacion, autorizacion)
        mock_validar.assert_called_once_with(
            cliente=cliente,
            total_venta=D("150.00"),
            fecha_venta=date(2026, 1, 1),
            request=contexto.credito_request,
            venta_existente=None,
        )

    def test_validar_no_consulta_credito_si_esta_desactivado(self):
        cliente = self.crear_cliente(nombre="Cliente crédito desactivado")
        service = VentaCreditoService(cliente=cliente, validar_credito=False)

        with patch("ventas.services.venta_credito.validar_credito_cliente_para_venta") as mock_validar:
            errores = service.validar([])

        self.assertEqual(errores, [])
        mock_validar.assert_not_called()

    def test_marcar_usada_delega_autorizacion(self):
        cliente = self.crear_cliente(nombre="Cliente crédito usada")
        service = VentaCreditoService(cliente=cliente)
        service.autorizacion = object()
        venta = object()

        with patch("ventas.services.venta_credito.marcar_autorizacion_credito_usada") as mock_marcar:
            service.marcar_usada(venta)

        mock_marcar.assert_called_once_with(service.autorizacion, venta)
