import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from catalogos.models import Cliente
from cartera.models import FacturaCliente
from cartera.selectors.facturacion import get_facturacion_cliente_resumen
from cartera.services.facturacion import cancelar_factura_cliente, extraer_datos_cfdi, registrar_factura_cliente


TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="cartera_facturacion_tests_")

CFDI_XML = b'''<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" Version="4.0" Serie="A" Folio="123" Fecha="2026-06-30T10:30:00" FormaPago="03" MetodoPago="PUE" Moneda="MXN" TipoDeComprobante="I" SubTotal="100.00" Total="116.00">
  <cfdi:Emisor Rfc="AAA010101AAA" Nombre="REGIMAR" RegimenFiscal="601" />
  <cfdi:Receptor Rfc="XAXX010101000" Nombre="CLIENTE PUBLICO" DomicilioFiscalReceptor="21376" RegimenFiscalReceptor="616" UsoCFDI="G03" />
  <cfdi:Impuestos TotalImpuestosTrasladados="16.00" />
  <cfdi:Complemento>
    <tfd:TimbreFiscalDigital UUID="11111111-1111-1111-1111-111111111111" FechaTimbrado="2026-06-30T10:31:00" />
  </cfdi:Complemento>
</cfdi:Comprobante>
'''


def xml_upload(name="factura.xml", content=CFDI_XML):
    return SimpleUploadedFile(name, content, content_type="application/xml")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class FacturacionCarteraTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.cliente = Cliente.objects.create(
            rfc="XAXX010101000",
            nombre_fiscal="CLIENTE PUBLICO",
            domicilio_fiscal_cp="21376",
        )
        self.usuario = get_user_model().objects.create_user(username="facturacion", password="test")

    def test_extrae_datos_cfdi_40(self):
        datos = extraer_datos_cfdi(xml_upload())

        self.assertEqual(datos["uuid"], "11111111-1111-1111-1111-111111111111")
        self.assertEqual(datos["serie"], "A")
        self.assertEqual(datos["folio"], "123")
        self.assertEqual(datos["rfc_receptor"], "XAXX010101000")
        self.assertEqual(datos["total"].to_eng_string(), "116.00")
        self.assertEqual(datos["impuestos_trasladados"].to_eng_string(), "16.00")

    def test_registra_factura_sin_afectar_cartera_y_bloquea_duplicado_activo(self):
        factura = registrar_factura_cliente(
            cliente=self.cliente,
            xml_file=xml_upload(),
            monto=Decimal("100.00"),
            usuario=self.usuario,
            referencia="OC-1",
        )

        self.assertEqual(factura.estado, FacturaCliente.ESTADO_ACTIVA)
        self.assertEqual(factura.cliente, self.cliente)
        self.assertEqual(factura.tipo_aplicacion, FacturaCliente.TIPO_GLOBAL)
        self.assertEqual(factura.total, Decimal("100.00"))
        self.assertEqual(factura.total_xml, Decimal("116.00"))
        self.assertTrue(factura.xml.name.endswith(".xml"))
        self.assertEqual(factura.aplicaciones.count(), 0)

        with self.assertRaises(ValidationError):
            registrar_factura_cliente(cliente=self.cliente, xml_file=xml_upload("duplicada.xml"), usuario=self.usuario)

    def test_cancelacion_interna_conserva_xml_y_libera_uuid_para_nuevo_control(self):
        factura = registrar_factura_cliente(cliente=self.cliente, xml_file=xml_upload(), usuario=self.usuario)
        xml_name = factura.xml.name

        cancelar_factura_cliente(factura, self.usuario, "Error de captura")
        factura.refresh_from_db()

        self.assertEqual(factura.estado, FacturaCliente.ESTADO_CANCELADA)
        self.assertEqual(factura.xml.name, xml_name)
        self.assertEqual(factura.cancelado_por, self.usuario)

        nueva = registrar_factura_cliente(cliente=self.cliente, xml_file=xml_upload("nueva.xml"), usuario=self.usuario)
        self.assertEqual(nueva.uuid, factura.uuid)

    def test_resumen_facturacion_cliente(self):
        factura = registrar_factura_cliente(cliente=self.cliente, xml_file=xml_upload(), usuario=self.usuario)
        resumen = get_facturacion_cliente_resumen(self.cliente)
        self.assertEqual(resumen["cantidad_facturas"], 1)
        self.assertEqual(resumen["total_facturado_activo"], factura.total)
        self.assertEqual(resumen["total_global"], factura.total)
        self.assertEqual(resumen["total_notas"], Decimal("0.00"))

        cancelar_factura_cliente(factura, self.usuario, "Error de captura")
        resumen = get_facturacion_cliente_resumen(self.cliente)
        self.assertEqual(resumen["cantidad_activas"], 0)
        self.assertEqual(resumen["total_cancelado"], factura.total)
