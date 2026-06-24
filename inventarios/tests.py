from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from catalogos.models import (
    Almacen,
    Cliente,
    PrecioMenorMinimoAutorizacion,
    Producto,
    ProductoMetricaConversion,
    Proveedor,
)
from inventarios.models import (
    EntradaInventario,
    EntradaInventarioDetalle,
    InventarioStock,
    SalidaInventario,
    SalidaInventarioDetalle,
    SalidaInventarioDetalleAlmacen,
)
from inventarios.services.ajustes import (
    AjusteInventarioService,
    TIPO_AJUSTE_NEGATIVO,
    TIPO_AJUSTE_POSITIVO,
)
from inventarios.services.costos import (
    aplicar_entrada_con_costo,
    costo_promedio_almacen,
    costo_virtual_producto,
)
from inventarios.services.entradas_manual import EntradaManualInventarioService
from inventarios.services.reversas import ReversaInventarioService
from inventarios.services.stock import aplicar_movimiento_stock, validar_stock_suficiente
from inventarios.services.traspasos import TraspasoInventarioService
from ventas.services.venta_credito import VentaCreditoService
from ventas.services.venta_data import VentaOperacionData, VentaRequestContext
from ventas.services.venta_precio import VentaPrecioMinimoService
from ventas.services.ventas import VentaService, es_almacen_venta_virtual


D = Decimal


class InventarioFactoryMixin:
    """Objetos mínimos para probar servicios de inventario sin depender de vistas."""

    def crear_producto(self, nombre="Producto prueba", **kwargs):
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

    def crear_almacen(self, codigo="ALM", nombre="Almacén", **kwargs):
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

    def crear_proveedor(self, nombre="Proveedor prueba"):
        return Proveedor.objects.create(nombre=nombre)

    def crear_cliente(self, nombre="Cliente prueba", **kwargs):
        defaults = {
            "nombre_fiscal": nombre,
            "nombre_comercial": nombre,
        }
        defaults.update(kwargs)
        return Cliente.objects.create(**defaults)

    def crear_conversion_caja(self, producto, factor="20.00"):
        return ProductoMetricaConversion.objects.create(
            producto=producto,
            nombre="Caja 20 kg",
            unidad_origen="Caja",
            cantidad_origen=D("1.00"),
            factor_conversion=D(factor),
            activo=True,
        )

    def entrada_form_fake(self, *, folio, proveedor, almacen):
        class EntradaManualFormFake:
            cleaned_data = {}

            def save(self, commit=True):
                entrada = EntradaInventario(
                    folio=folio,
                    fecha=timezone.localdate(),
                    proveedor=proveedor,
                    almacen=almacen,
                    documento_referencia="REM-001",
                    observaciones="Entrada de prueba",
                )
                if commit:
                    entrada.save()
                return entrada

        return EntradaManualFormFake()


class StockServiceTests(InventarioFactoryMixin, TestCase):
    def setUp(self):
        self.producto = self.crear_producto()
        self.almacen = self.crear_almacen()

    def test_aplicar_movimiento_stock_suma_y_resta_existencias(self):
        aplicar_movimiento_stock(
            producto_id=self.producto.id,
            almacen_id=self.almacen.id,
            delta=D("10.00"),
        )
        aplicar_movimiento_stock(
            producto_id=self.producto.id,
            almacen_id=self.almacen.id,
            delta=D("-3.50"),
        )

        stock = InventarioStock.objects.get(producto=self.producto, almacen=self.almacen)
        self.producto.refresh_from_db()

        self.assertEqual(stock.cantidad, D("6.50"))
        self.assertEqual(self.producto.stock, D("6.50"))

    def test_aplicar_movimiento_stock_no_permite_stock_negativo(self):
        aplicar_movimiento_stock(
            producto_id=self.producto.id,
            almacen_id=self.almacen.id,
            delta=D("2.00"),
        )

        with self.assertRaises(IntegrityError):
            aplicar_movimiento_stock(
                producto_id=self.producto.id,
                almacen_id=self.almacen.id,
                delta=D("-3.00"),
            )

        stock = InventarioStock.objects.get(producto=self.producto, almacen=self.almacen)
        self.producto.refresh_from_db()
        self.assertEqual(stock.cantidad, D("2.00"))
        self.assertEqual(self.producto.stock, D("2.00"))

    def test_validar_stock_suficiente_detecta_faltantes(self):
        aplicar_movimiento_stock(
            producto_id=self.producto.id,
            almacen_id=self.almacen.id,
            delta=D("4.00"),
        )

        ok, disponibles, faltantes = validar_stock_suficiente(
            almacen_id=self.almacen.id,
            requeridos={self.producto.id: D("5.00")},
        )

        self.assertFalse(ok)
        self.assertEqual(disponibles[self.producto.id], D("4.00"))
        self.assertEqual(faltantes[self.producto.id], D("5.00"))


class CostosServiceTests(InventarioFactoryMixin, TestCase):
    def setUp(self):
        self.producto = self.crear_producto()
        self.almacen = self.crear_almacen()

    def test_aplicar_entrada_con_costo_calcula_promedio_ponderado(self):
        aplicar_entrada_con_costo(
            producto_id=self.producto.id,
            almacen_id=self.almacen.id,
            cantidad=D("10.00"),
            costo_unitario=D("20.00"),
        )
        aplicar_entrada_con_costo(
            producto_id=self.producto.id,
            almacen_id=self.almacen.id,
            cantidad=D("10.00"),
            costo_unitario=D("30.00"),
        )

        stock = InventarioStock.objects.get(producto=self.producto, almacen=self.almacen)
        self.producto.refresh_from_db()

        self.assertEqual(stock.cantidad, D("20.00"))
        self.assertEqual(stock.costo_promedio, D("25.00"))
        self.assertEqual(self.producto.stock, D("20.00"))
        self.assertEqual(self.producto.costo_promedio, D("25.00"))
        self.assertEqual(self.producto.ultimo_costo_compra, D("30.00"))
        self.assertEqual(self.producto.fecha_ultima_compra, timezone.localdate())

    def test_costo_promedio_producto_considera_varios_almacenes(self):
        almacen_2 = self.crear_almacen(codigo="ALM2", nombre="Almacén 2")

        aplicar_entrada_con_costo(
            producto_id=self.producto.id,
            almacen_id=self.almacen.id,
            cantidad=D("5.00"),
            costo_unitario=D("10.00"),
        )
        aplicar_entrada_con_costo(
            producto_id=self.producto.id,
            almacen_id=almacen_2.id,
            cantidad=D("15.00"),
            costo_unitario=D("30.00"),
        )

        self.producto.refresh_from_db()
        self.assertEqual(costo_promedio_almacen(producto_id=self.producto.id, almacen_id=self.almacen.id), D("10.00"))
        self.assertEqual(costo_promedio_almacen(producto_id=self.producto.id, almacen_id=almacen_2.id), D("30.00"))
        self.assertEqual(self.producto.costo_promedio, D("25.00"))

    def test_costo_virtual_prioriza_ultimo_costo_y_luego_promedio(self):
        producto = self.crear_producto(
            nombre="Producto virtual",
            ultimo_costo_compra=D("12.00"),
            costo_promedio=D("9.00"),
        )
        self.assertEqual(costo_virtual_producto(producto), D("12.00"))

        producto.ultimo_costo_compra = D("0.00")
        producto.save(update_fields=["ultimo_costo_compra"])
        producto.refresh_from_db()
        self.assertEqual(costo_virtual_producto(producto), D("9.00"))


class EntradaManualInventarioServiceTests(InventarioFactoryMixin, TestCase):
    def setUp(self):
        self.producto = self.crear_producto()
        self.almacen = self.crear_almacen()
        self.proveedor = self.crear_proveedor()
        self.conversion = self.crear_conversion_caja(self.producto, factor="20.00")
        self.service = EntradaManualInventarioService()

    def test_normalizar_detalle_convierte_presentacion_a_metrica_base(self):
        detalle = [
            {
                "producto_id": self.producto.id,
                "almacen_id": self.almacen.id,
                "cantidad": "2",
                "conversion_id": str(self.conversion.id),
                "costo_unitario": "50.00",
            }
        ]

        normalizado = self.service.normalizar_detalle(detalle)

        self.assertEqual(len(normalizado), 1)
        linea = normalizado[0]
        self.assertEqual(linea["cantidad"], D("40.00"))
        self.assertEqual(linea["cantidad_presentacion"], D("2"))
        self.assertEqual(linea["presentacion_conversion_id"], str(self.conversion.id))
        self.assertEqual(linea["presentacion_factor_conversion"], D("20.00"))
        self.assertEqual(linea["costo_total"], D("2000.0000"))

    def test_registrar_desde_form_crea_entrada_detalle_stock_y_costo(self):
        form = self.entrada_form_fake(
            folio="MAN-TEST-001",
            proveedor=self.proveedor,
            almacen=self.almacen,
        )
        detalle = [
            {
                "producto_id": self.producto.id,
                "almacen_id": self.almacen.id,
                "cantidad": "2",
                "conversion_id": str(self.conversion.id),
                "costo_unitario": "50.00",
            }
        ]

        resultado = self.service.registrar_desde_form(form=form, detalle_json=detalle)

        entrada = resultado.entrada
        self.assertEqual(entrada.tipo, EntradaInventario.TIPO_ENTRADA_MANUAL)
        self.assertEqual(entrada.detalles.count(), 1)

        detalle_creado = entrada.detalles.get()
        stock = InventarioStock.objects.get(producto=self.producto, almacen=self.almacen)
        self.producto.refresh_from_db()

        self.assertEqual(detalle_creado.cantidad, D("40.00"))
        self.assertEqual(detalle_creado.costo_unitario, D("50.00"))
        self.assertEqual(stock.cantidad, D("40.00"))
        self.assertEqual(stock.costo_promedio, D("50.00"))
        self.assertEqual(self.producto.stock, D("40.00"))
        self.assertEqual(self.producto.costo_promedio, D("50.00"))

    def test_registrar_desde_form_rechaza_detalle_vacio(self):
        form = self.entrada_form_fake(
            folio="MAN-TEST-002",
            proveedor=self.proveedor,
            almacen=self.almacen,
        )

        with self.assertRaisesMessage(ValueError, "Debes agregar al menos un producto"):
            self.service.registrar_desde_form(form=form, detalle_json=[])


class AjusteInventarioServiceTests(InventarioFactoryMixin, TestCase):
    def setUp(self):
        self.producto = self.crear_producto()
        self.almacen = self.crear_almacen()
        self.service = AjusteInventarioService()

    def test_ajuste_positivo_suma_stock_y_crea_entrada(self):
        resultado = self.service.aplicar(
            data={
                "folio": "AJP-TEST-001",
                "fecha": timezone.localdate(),
                "producto": self.producto,
                "cantidad": D("5.00"),
                "precio_unitario": D("40.00"),
                "tipo_ajuste": TIPO_AJUSTE_POSITIVO,
                "motivo": "Inventario inicial",
                "observaciones": "Prueba",
            },
            almacen=self.almacen,
        )

        entrada = resultado.movimiento
        stock = InventarioStock.objects.get(producto=self.producto, almacen=self.almacen)
        self.producto.refresh_from_db()

        self.assertEqual(entrada.tipo, EntradaInventario.TIPO_AJUSTE_POSITIVO)
        self.assertEqual(entrada.detalles.get().cantidad, D("5.00"))
        self.assertEqual(stock.cantidad, D("5.00"))
        self.assertEqual(self.producto.stock, D("5.00"))

    def test_ajuste_negativo_descuenta_stock_y_crea_salida(self):
        aplicar_entrada_con_costo(
            producto_id=self.producto.id,
            almacen_id=self.almacen.id,
            cantidad=D("10.00"),
            costo_unitario=D("20.00"),
        )

        resultado = self.service.aplicar(
            data={
                "folio": "AJN-TEST-001",
                "fecha": timezone.localdate(),
                "producto": self.producto,
                "cantidad": D("4.00"),
                "precio_unitario": D("20.00"),
                "tipo_ajuste": TIPO_AJUSTE_NEGATIVO,
                "motivo": "Merma",
                "observaciones": "Prueba",
            },
            almacen=self.almacen,
        )

        salida = resultado.movimiento
        stock = InventarioStock.objects.get(producto=self.producto, almacen=self.almacen)
        self.producto.refresh_from_db()

        self.assertEqual(salida.tipo, SalidaInventario.TIPO_AJUSTE_NEGATIVO)
        self.assertEqual(salida.detalles.get().cantidad, D("4.00"))
        self.assertEqual(stock.cantidad, D("6.00"))
        self.assertEqual(self.producto.stock, D("6.00"))

    def test_ajuste_cero_no_se_puede_aplicar(self):
        with self.assertRaisesMessage(ValueError, "La cantidad debe ser mayor a 0"):
            self.service.aplicar(
                data={
                    "folio": "AJP-TEST-002",
                    "fecha": timezone.localdate(),
                    "producto": self.producto,
                    "cantidad": D("0.00"),
                    "precio_unitario": D("20.00"),
                    "tipo_ajuste": TIPO_AJUSTE_POSITIVO,
                    "motivo": "",
                    "observaciones": "",
                },
                almacen=self.almacen,
            )

    def test_ajuste_negativo_no_permite_dejar_inventario_negativo(self):
        aplicar_entrada_con_costo(
            producto_id=self.producto.id,
            almacen_id=self.almacen.id,
            cantidad=D("2.00"),
            costo_unitario=D("20.00"),
        )

        with self.assertRaisesMessage(ValueError, "Stock insuficiente"):
            self.service.aplicar(
                data={
                    "folio": "AJN-TEST-002",
                    "fecha": timezone.localdate(),
                    "producto": self.producto,
                    "cantidad": D("3.00"),
                    "precio_unitario": D("20.00"),
                    "tipo_ajuste": TIPO_AJUSTE_NEGATIVO,
                    "motivo": "",
                    "observaciones": "",
                },
                almacen=self.almacen,
            )


class ReversaInventarioServiceTests(InventarioFactoryMixin, TestCase):
    def setUp(self):
        self.producto = self.crear_producto()
        self.almacen = self.crear_almacen()
        self.proveedor = self.crear_proveedor()
        self.entrada_service = EntradaManualInventarioService()
        self.ajuste_service = AjusteInventarioService()
        self.reversa_service = ReversaInventarioService()

    def test_reversar_entrada_manual_crea_salida_y_restaura_stock(self):
        form = self.entrada_form_fake(
            folio="MAN-REV-001",
            proveedor=self.proveedor,
            almacen=self.almacen,
        )
        resultado_entrada = self.entrada_service.registrar_desde_form(
            form=form,
            detalle_json=[
                {
                    "producto_id": self.producto.id,
                    "almacen_id": self.almacen.id,
                    "cantidad": "8",
                    "costo_unitario": "10.00",
                }
            ],
        )

        resultado_reversa = self.reversa_service.reversar_entrada_manual(
            entrada_id=resultado_entrada.entrada.id,
        )

        salida_reversa = resultado_reversa.movimiento_reversa
        stock = InventarioStock.objects.get(producto=self.producto, almacen=self.almacen)
        self.producto.refresh_from_db()

        self.assertEqual(salida_reversa.tipo, SalidaInventario.TIPO_AJUSTE_NEGATIVO)
        self.assertIn("REVERSA_DE=entrada_manual", salida_reversa.observaciones)
        self.assertEqual(stock.cantidad, D("0.00"))
        self.assertEqual(self.producto.stock, D("0.00"))

        with self.assertRaisesMessage(ValueError, "ya tiene una reversa"):
            self.reversa_service.reversar_entrada_manual(entrada_id=resultado_entrada.entrada.id)

    def test_reversar_ajuste_positivo_crea_salida_compensatoria(self):
        ajuste = self.ajuste_service.aplicar(
            data={
                "folio": "AJP-REV-001",
                "fecha": timezone.localdate(),
                "producto": self.producto,
                "cantidad": D("5.00"),
                "precio_unitario": D("20.00"),
                "tipo_ajuste": TIPO_AJUSTE_POSITIVO,
                "motivo": "Ajuste",
                "observaciones": "",
            },
            almacen=self.almacen,
        )

        reversa = self.reversa_service.reversar_ajuste(
            tipo="entrada",
            movimiento_id=ajuste.movimiento.id,
        )

        stock = InventarioStock.objects.get(producto=self.producto, almacen=self.almacen)
        self.producto.refresh_from_db()
        self.assertEqual(reversa.movimiento_reversa.tipo, SalidaInventario.TIPO_AJUSTE_NEGATIVO)
        self.assertIn("REVERSA_DE=entrada", reversa.movimiento_reversa.observaciones)
        self.assertEqual(stock.cantidad, D("0.00"))
        self.assertEqual(self.producto.stock, D("0.00"))

    def test_reversar_ajuste_negativo_crea_entrada_compensatoria(self):
        aplicar_entrada_con_costo(
            producto_id=self.producto.id,
            almacen_id=self.almacen.id,
            cantidad=D("10.00"),
            costo_unitario=D("15.00"),
        )
        ajuste = self.ajuste_service.aplicar(
            data={
                "folio": "AJN-REV-001",
                "fecha": timezone.localdate(),
                "producto": self.producto,
                "cantidad": D("4.00"),
                "precio_unitario": D("15.00"),
                "tipo_ajuste": TIPO_AJUSTE_NEGATIVO,
                "motivo": "Ajuste",
                "observaciones": "",
            },
            almacen=self.almacen,
        )

        reversa = self.reversa_service.reversar_ajuste(
            tipo="salida",
            movimiento_id=ajuste.movimiento.id,
        )

        stock = InventarioStock.objects.get(producto=self.producto, almacen=self.almacen)
        self.producto.refresh_from_db()
        self.assertEqual(reversa.movimiento_reversa.tipo, EntradaInventario.TIPO_AJUSTE_POSITIVO)
        self.assertIn("REVERSA_DE=salida", reversa.movimiento_reversa.observaciones)
        self.assertEqual(stock.cantidad, D("10.00"))
        self.assertEqual(self.producto.stock, D("10.00"))


class TraspasoInventarioServiceTests(InventarioFactoryMixin, TestCase):
    def setUp(self):
        self.producto = self.crear_producto()
        self.origen = self.crear_almacen(codigo="ORI", nombre="Origen")
        self.destino = self.crear_almacen(codigo="DES", nombre="Destino")
        self.service = TraspasoInventarioService()

    def test_traspaso_descuenta_origen_suma_destino_y_crea_movimientos(self):
        aplicar_entrada_con_costo(
            producto_id=self.producto.id,
            almacen_id=self.origen.id,
            cantidad=D("10.00"),
            costo_unitario=D("22.00"),
        )

        resultado = self.service.ejecutar(
            data={
                "producto": self.producto,
                "almacen_origen": self.origen,
                "almacen_destino": self.destino,
                "cantidad": D("3.00"),
                "fecha": timezone.localdate(),
                "folio_salida": "TRS-TEST-001",
                "folio_entrada": "TRE-TEST-001",
                "motivo": "Reubicación",
                "observaciones": "Prueba",
            }
        )

        stock_origen = InventarioStock.objects.get(producto=self.producto, almacen=self.origen)
        stock_destino = InventarioStock.objects.get(producto=self.producto, almacen=self.destino)
        self.producto.refresh_from_db()

        self.assertEqual(resultado.salida.tipo, SalidaInventario.TIPO_TRASLADO_SALIDA)
        self.assertEqual(resultado.entrada.tipo, EntradaInventario.TIPO_TRASLADO)
        self.assertEqual(stock_origen.cantidad, D("7.00"))
        self.assertEqual(stock_destino.cantidad, D("3.00"))
        self.assertEqual(stock_destino.costo_promedio, D("22.00"))
        self.assertEqual(self.producto.stock, D("10.00"))
        self.assertIn("TRASPASO_ENTRADA", resultado.salida.observaciones)
        self.assertIn("TRASPASO_SALIDA", resultado.entrada.observaciones)

    def test_traspaso_no_permite_mismo_almacen(self):
        with self.assertRaisesMessage(IntegrityError, "diferente"):
            self.service.ejecutar(
                data={
                    "producto": self.producto,
                    "almacen_origen": self.origen,
                    "almacen_destino": self.origen,
                    "cantidad": D("1.00"),
                    "fecha": timezone.localdate(),
                    "folio_salida": "TRS-TEST-002",
                    "folio_entrada": "TRE-TEST-002",
                    "motivo": "",
                    "observaciones": "",
                }
            )


class VentaServiceTests(InventarioFactoryMixin, TestCase):
    def crear_detalle_venta(self, *, producto, cantidad, precio="100.00"):
        return SalidaInventarioDetalle(
            producto=producto,
            cantidad=D(cantidad),
            precio_unitario=D(precio),
        )

    def crear_venta_service(self, *, salida, detalle, almacen, validar_credito=False):
        data = VentaOperacionData(
            salida=salida,
            cliente=None,
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

    def test_venta_fisica_valida_y_descuenta_stock(self):
        producto = self.crear_producto(nombre="Producto venta", costo_promedio=D("20.00"))
        almacen = self.crear_almacen(codigo="VTA", nombre="Ventas")
        aplicar_entrada_con_costo(
            producto_id=producto.id,
            almacen_id=almacen.id,
            cantidad=D("10.00"),
            costo_unitario=D("20.00"),
        )
        salida = SalidaInventario(
            folio="VTA-TEST-001",
            fecha=timezone.localdate(),
            tipo=SalidaInventario.TIPO_VENTA,
            cliente="Cliente mostrador",
        )
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
        producto = self.crear_producto(nombre="Producto sin stock")
        almacen = self.crear_almacen(codigo="SIN", nombre="Sin stock")
        salida = SalidaInventario(
            folio="VTA-TEST-002",
            fecha=timezone.localdate(),
            tipo=SalidaInventario.TIPO_VENTA,
            cliente="Cliente mostrador",
        )
        detalle = self.crear_detalle_venta(producto=producto, cantidad="1.00", precio="100.00")
        service = self.crear_venta_service(salida=salida, detalle=detalle, almacen=almacen)

        errores = service.validar_stock()

        self.assertEqual(len(errores), 1)
        self.assertIn("Stock insuficiente", errores[0])

    def test_venta_virtual_genera_entrada_y_salida_sin_dejar_stock_negativo(self):
        producto = self.crear_producto(
            nombre="Producto virtual venta",
            ultimo_costo_compra=D("12.00"),
            costo_promedio=D("12.00"),
        )
        almacen_virtual = self.crear_almacen(
            codigo="VIRT",
            nombre="Virtual",
            tipo="VIRTUAL",
            es_virtual_sistema=True,
        )
        salida = SalidaInventario(
            folio="VTA-VIRT-001",
            fecha=timezone.localdate(),
            tipo=SalidaInventario.TIPO_VENTA,
            cliente="Cliente mostrador",
        )
        detalle = self.crear_detalle_venta(producto=producto, cantidad="5.00", precio="100.00")
        service = self.crear_venta_service(salida=salida, detalle=detalle, almacen=almacen_virtual)

        self.assertTrue(es_almacen_venta_virtual(almacen_virtual))
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


class VentaPrecioMinimoServiceTests(InventarioFactoryMixin, TestCase):
    def setUp(self):
        self.cliente = self.crear_cliente()
        self.producto = self.crear_producto(
            nombre="Producto precio mínimo",
            precio=D("100.00"),
            precio_minimo=D("80.00"),
        )
        self.detalle = SalidaInventarioDetalle(
            producto=self.producto,
            cantidad=D("1.00"),
            precio_unitario=D("70.00"),
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
        notificador.enviar_solicitud.assert_called_once()


class VentaCreditoServiceTests(InventarioFactoryMixin, TestCase):
    def test_validar_delega_en_servicio_de_credito_y_guarda_autorizacion(self):
        cliente = self.crear_cliente(limite_credito=D("100.00"))
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
        mock_validar.assert_called_once()

    def test_marcar_usada_delega_autorizacion(self):
        cliente = self.crear_cliente()
        service = VentaCreditoService(cliente=cliente)
        service.autorizacion = object()
        venta = object()

        with patch("ventas.services.venta_credito.marcar_autorizacion_credito_usada") as mock_marcar:
            service.marcar_usada(venta)

        mock_marcar.assert_called_once_with(service.autorizacion, venta)
