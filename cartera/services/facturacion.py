import hashlib
from datetime import datetime
from decimal import Decimal, InvalidOperation
from xml.dom import minidom
from xml.etree import ElementTree

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from cartera.models import FacturaAplicacionNota, FacturaCliente
from cartera.selectors.cartera import get_total_nota
from ventas.models import NotaVenta

TWOPLACES = Decimal("0.01")


def _money(value):
    try:
        return Decimal(value or "0").quantize(TWOPLACES)
    except (InvalidOperation, TypeError):
        raise ValidationError("El XML contiene importes inválidos.")


def _read_xml_bytes(xml_file):
    if isinstance(xml_file, bytes):
        return xml_file
    if isinstance(xml_file, str):
        return xml_file.encode("utf-8")
    position = None
    if hasattr(xml_file, "tell") and hasattr(xml_file, "seek"):
        try:
            position = xml_file.tell()
            xml_file.seek(0)
        except (OSError, ValueError):
            position = None
    data = xml_file.read()
    if isinstance(data, str):
        data = data.encode("utf-8")
    if position is not None:
        xml_file.seek(position)
    return data


def _local_name(tag):
    return tag.rsplit("}", 1)[-1]


def _find_first(root, local_name):
    for elem in root.iter():
        if _local_name(elem.tag) == local_name:
            return elem
    return None


def _find_timbre(root):
    for elem in root.iter():
        if _local_name(elem.tag) == "TimbreFiscalDigital":
            return elem
    return None


def _parse_fecha(value):
    if not value:
        raise ValidationError("El XML no contiene fecha de emisión.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValidationError("La fecha de emisión del XML no es válida.")
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed)
    return parsed


def extraer_datos_cfdi(xml_file):
    xml_bytes = _read_xml_bytes(xml_file)
    if not xml_bytes:
        raise ValidationError("El XML es obligatorio.")
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as exc:
        raise ValidationError(f"El XML no está bien formado: {exc}.")

    if _local_name(root.tag) != "Comprobante":
        raise ValidationError("El archivo no parece ser un CFDI: falta el nodo Comprobante.")

    emisor = _find_first(root, "Emisor")
    receptor = _find_first(root, "Receptor")
    timbre = _find_timbre(root)
    if emisor is None or receptor is None:
        raise ValidationError("El CFDI debe contener nodos Emisor y Receptor.")
    if timbre is None or not timbre.attrib.get("UUID"):
        raise ValidationError("El CFDI debe contener TimbreFiscalDigital con UUID.")

    impuestos = _find_first(root, "Impuestos")
    total_trasladados = Decimal("0.00")
    total_retenidos = Decimal("0.00")
    if impuestos is not None:
        total_trasladados = _money(impuestos.attrib.get("TotalImpuestosTrasladados"))
        total_retenidos = _money(impuestos.attrib.get("TotalImpuestosRetenidos"))

    return {
        "fecha": _parse_fecha(root.attrib.get("Fecha")),
        "uuid": (timbre.attrib.get("UUID") or "").upper(),
        "serie": root.attrib.get("Serie", ""),
        "folio": root.attrib.get("Folio", ""),
        "tipo_comprobante": root.attrib.get("TipoDeComprobante", ""),
        "moneda": root.attrib.get("Moneda", ""),
        "subtotal": _money(root.attrib.get("SubTotal")),
        "descuento": _money(root.attrib.get("Descuento")),
        "impuestos_trasladados": total_trasladados,
        "impuestos_retenidos": total_retenidos,
        "total": _money(root.attrib.get("Total")),
        "rfc_emisor": (emisor.attrib.get("Rfc") or emisor.attrib.get("rfc") or "").upper(),
        "nombre_emisor": emisor.attrib.get("Nombre", ""),
        "rfc_receptor": (receptor.attrib.get("Rfc") or receptor.attrib.get("rfc") or "").upper(),
        "nombre_receptor": receptor.attrib.get("Nombre", ""),
        "uso_cfdi": receptor.attrib.get("UsoCFDI", ""),
        "forma_pago": root.attrib.get("FormaPago", ""),
        "metodo_pago": root.attrib.get("MetodoPago", ""),
        "version": root.attrib.get("Version") or root.attrib.get("version") or "",
    }


def leer_xml_factura(factura):
    if not factura.xml:
        return ""
    with factura.xml.open("rb") as fh:
        data = fh.read()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="replace")


def pretty_xml_factura(factura):
    raw = leer_xml_factura(factura)
    if not raw:
        return ""
    try:
        parsed = minidom.parseString(raw.encode("utf-8"))
        pretty = parsed.toprettyxml(indent="  ")
        lines = [line for line in pretty.splitlines() if line.strip()]
        return "\n".join(lines)
    except Exception:
        return raw


def calcular_xml_hash(xml_file):
    return hashlib.sha256(_read_xml_bytes(xml_file)).hexdigest()


def validar_factura_cliente(cliente, datos_cfdi, xml_hash=None, factura_id=None):
    if datos_cfdi["total"] <= 0:
        raise ValidationError("El total del XML debe ser mayor a cero.")
    if cliente.rfc and datos_cfdi.get("rfc_receptor") and cliente.rfc.upper() != datos_cfdi["rfc_receptor"].upper():
        raise ValidationError("El RFC receptor del XML no coincide con el cliente seleccionado.")

    qs = FacturaCliente.objects.filter(estado=FacturaCliente.ESTADO_ACTIVA)
    if factura_id:
        qs = qs.exclude(pk=factura_id)
    if qs.filter(uuid=datos_cfdi["uuid"]).exists():
        raise ValidationError("Ya existe una factura activa con ese UUID.")
    if xml_hash and qs.filter(xml_hash=xml_hash).exists():
        raise ValidationError("Ya existe una factura activa con el mismo archivo XML.")


def _normalizar_monto(monto, mensaje="El monto debe ser mayor a cero."):
    monto = _money(monto)
    if monto <= 0:
        raise ValidationError(mensaje)
    return monto


def _normalizar_aplicaciones(aplicaciones):
    limpias = []
    notas_vistas = set()
    for item in aplicaciones or []:
        nota_ref = item.get("nota_id") or item.get("nota_venta_id")
        nota_id = getattr(nota_ref, "pk", nota_ref)
        monto_raw = item.get("monto") or item.get("monto_facturado")
        if not nota_id and not monto_raw:
            continue
        if not nota_id:
            raise ValidationError("Selecciona la nota para cada aplicación capturada.")
        monto = _normalizar_monto(monto_raw, "El monto facturado por nota debe ser mayor a cero.")
        if nota_id in notas_vistas:
            raise ValidationError("No repitas la misma nota dentro de la misma factura.")
        notas_vistas.add(nota_id)
        limpias.append({"nota_id": nota_id, "monto": monto, "observaciones": item.get("observaciones", "")})
    return limpias


def _total_facturado_activo_nota(nota):
    return (
        FacturaAplicacionNota.objects.filter(
            nota_venta=nota,
            factura__estado=FacturaCliente.ESTADO_ACTIVA,
        ).aggregate(total=Sum("monto_facturado"))["total"]
        or Decimal("0.00")
    )


def _validar_aplicaciones(cliente, aplicaciones_limpias, monto_factura, tipo_aplicacion):
    total_aplicado = sum((item["monto"] for item in aplicaciones_limpias), Decimal("0.00"))

    if tipo_aplicacion == FacturaCliente.TIPO_GLOBAL:
        if aplicaciones_limpias:
            raise ValidationError("Para una factura global no captures notas relacionadas.")
        return total_aplicado

    if tipo_aplicacion == FacturaCliente.TIPO_NOTAS:
        if not aplicaciones_limpias:
            raise ValidationError("Selecciona al menos una nota cuando la factura se aplica a notas.")
        if total_aplicado != monto_factura:
            raise ValidationError("La suma aplicada a notas debe ser igual al monto de la factura.")

    for item in aplicaciones_limpias:
        nota = NotaVenta.objects.select_for_update().get(pk=item["nota_id"])
        if nota.cliente_ref_id != cliente.id:
            raise ValidationError("Todas las notas aplicadas deben pertenecer al cliente de la factura.")
        if nota.estado != NotaVenta.ESTADO_ACTIVA:
            raise ValidationError(f"La nota {nota.folio} no está activa.")
        total_nota = get_total_nota(nota)
        facturado_previo = _total_facturado_activo_nota(nota)
        disponible = max(total_nota - facturado_previo, Decimal("0.00"))
        if item["monto"] > disponible:
            raise ValidationError(f"El monto facturado para la nota {nota.folio} excede el disponible por facturar (${disponible:,.2f}).")
        item["nota"] = nota

    return total_aplicado


@transaction.atomic
def registrar_factura_cliente(cliente, xml_file, monto=None, tipo_aplicacion=FacturaCliente.TIPO_GLOBAL, aplicaciones=None, usuario=None, referencia="", observaciones=""):
    datos = extraer_datos_cfdi(xml_file)
    xml_hash = calcular_xml_hash(xml_file)
    validar_factura_cliente(cliente, datos, xml_hash=xml_hash)

    monto_factura = _normalizar_monto(monto if monto is not None else datos["total"], "El monto de la factura debe ser mayor a cero.")
    if tipo_aplicacion not in {FacturaCliente.TIPO_GLOBAL, FacturaCliente.TIPO_NOTAS}:
        raise ValidationError("Selecciona si la factura se aplicará global al cliente o a notas.")

    aplicaciones_limpias = _normalizar_aplicaciones(aplicaciones)
    _validar_aplicaciones(cliente, aplicaciones_limpias, monto_factura, tipo_aplicacion)

    factura = FacturaCliente.objects.create(
        cliente=cliente,
        fecha=datos["fecha"],
        uuid=datos["uuid"],
        serie=datos["serie"],
        folio=datos["folio"],
        tipo_comprobante=datos["tipo_comprobante"],
        tipo_aplicacion=tipo_aplicacion,
        moneda=datos["moneda"],
        subtotal=datos["subtotal"],
        descuento=datos["descuento"],
        impuestos_trasladados=datos["impuestos_trasladados"],
        impuestos_retenidos=datos["impuestos_retenidos"],
        total=monto_factura,
        total_xml=datos["total"],
        rfc_emisor=datos["rfc_emisor"],
        nombre_emisor=datos["nombre_emisor"],
        rfc_receptor=datos["rfc_receptor"],
        nombre_receptor=datos["nombre_receptor"],
        uso_cfdi=datos["uso_cfdi"],
        forma_pago=datos["forma_pago"],
        metodo_pago=datos["metodo_pago"],
        xml=xml_file,
        xml_hash=xml_hash,
        referencia=referencia,
        observaciones=observaciones,
        creado_por=usuario,
    )

    for item in aplicaciones_limpias:
        FacturaAplicacionNota.objects.create(
            factura=factura,
            nota_venta=item["nota"],
            monto_facturado=item["monto"],
            creado_por=usuario,
            observaciones=item["observaciones"],
        )
    return factura


@transaction.atomic
def cancelar_factura_cliente(factura, usuario, motivo):
    motivo = (motivo or "").strip()
    if len(motivo) < 8:
        raise ValidationError("Captura un motivo de cancelación interna de al menos 8 caracteres.")
    factura = FacturaCliente.objects.select_for_update().get(pk=factura.pk)
    if factura.estado == FacturaCliente.ESTADO_CANCELADA:
        raise ValidationError("La factura ya está cancelada internamente.")
    factura.estado = FacturaCliente.ESTADO_CANCELADA
    factura.cancelado_por = usuario
    factura.cancelado_en = timezone.now()
    factura.motivo_cancelacion = motivo
    factura.save(update_fields=["estado", "cancelado_por", "cancelado_en", "motivo_cancelacion"])
    return factura
