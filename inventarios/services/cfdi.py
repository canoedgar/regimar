import xml.etree.ElementTree as ET
from datetime import datetime

def parse_cfdi_header(xml_text: str):
    """
    Regresa datos de encabezado del CFDI:
    {
      "folio": str,
      "fecha": str (ISO date: YYYY-MM-DD)          <- para hidden/BD
      "fecha_display": str (YYYY-MM-DD HH:MM:SS)   <- para UI
      "uuid": str,
      "proveedor_nombre": str,
      "proveedor_rfc": str,
    }
    """
    root = ET.fromstring(xml_text)

    comprobante = root
    if not root.tag.endswith("Comprobante"):
        comprobante = root.find(".//{*}Comprobante")

    data = {
        "folio": "",
        "fecha": "",          # ISO YYYY-MM-DD
        "fecha_display": "",  # YYYY-MM-DD HH:MM:SS
        "uuid": "",
        "proveedor_nombre": "",
        "proveedor_rfc": "",
    }

    if comprobante is not None:
        serie = comprobante.attrib.get("Serie", "").strip()
        factura = comprobante.attrib.get("Folio", "").strip()
        if serie and factura:
            data["folio"] = f"{serie}-{factura}"
        else:
            data["folio"] = factura or serie or ""        

        raw_fecha = comprobante.attrib.get("Fecha", "").strip()

        # fecha ISO para backend/UI (YYYY-MM-DD)
        if raw_fecha:
            try:
                dt = datetime.strptime(raw_fecha, "%Y-%m-%dT%H:%M:%S")
                data["fecha"] = dt.strftime("%Y-%m-%d")
                data["fecha_display"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                
            except ValueError:
                # fallback si viene con fracciones o timezone (si aparece)                
                data["fecha"] = raw_fecha.split("T")[0] if "T" in raw_fecha else raw_fecha
                data["fecha_display"] = raw_fecha
                
        else:
            data["fecha"] = ""
            data["fecha_display"] = ""        

    emisor = root.find(".//{*}Emisor")
    if emisor is not None:
        data["proveedor_nombre"] = emisor.attrib.get("Nombre", "").strip()
        data["proveedor_rfc"] = emisor.attrib.get("Rfc", "").strip()

    timbre = root.find(".//{*}TimbreFiscalDigital")
    if timbre is not None:
        data["uuid"] = timbre.attrib.get("UUID", "").strip()

    return data


def parse_cfdi_xml(xml_text: str):
    """
    Regresa una lista de conceptos del CFDI:
    [
      {
        "clave_sat": str,
        "descripcion": str,
        "cantidad": Decimal (como str),
        "valor_unitario": Decimal (como str),
      },
      ...
    ]
    """
    conceptos = []

    root = ET.fromstring(xml_text)

    # Cualquier versión de CFDI: busca cualquier elemento Concepto
    for c in root.findall(".//{*}Concepto"):
        conceptos.append({
            "clave_sat": c.attrib.get("ClaveProdServ", "").strip(),
            "descripcion": c.attrib.get("Descripcion", "").strip(),
            "cantidad": c.attrib.get("Cantidad", "0").strip().rstrip("0").rstrip("."),
            "valor_unitario": c.attrib.get("ValorUnitario", "0").strip().rstrip("0").rstrip("."),
        })

    return conceptos
