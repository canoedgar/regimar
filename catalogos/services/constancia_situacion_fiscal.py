"""Lectura de Constancias de Situación Fiscal del SAT.

El servicio extrae únicamente datos que ya existen en el catálogo de clientes.
No valida la autenticidad fiscal del documento; solo usa el texto incluido en el PDF
para facilitar la captura manual.
"""

from __future__ import annotations

import io
import re
import unicodedata
from typing import Any

from catalogos.sat_catalogos import REGIMEN_FISCAL_CHOICES
from catalogos.services.regimenes_fiscales import codigos_regimenes_fiscales, regimen_fiscal_a_json


class ConstanciaFiscalPDFError(ValueError):
    """Error controlado al leer una Constancia de Situación Fiscal."""


REGIMENES_ESPECIALES = {
    "GENERAL LEY PERSONAS MORALES": "601",
    "PERSONAS MORALES FINES NO LUCRATIVOS": "603",
    "SUELDOS SALARIOS INGRESOS ASIMILADOS SALARIOS": "605",
    "ARRENDAMIENTO": "606",
    "ENAJENACION ADQUISICION BIENES": "607",
    "DEMAS INGRESOS": "608",
    "RESIDENTES EXTRANJERO SIN ESTABLECIMIENTO PERMANENTE MEXICO": "610",
    "INGRESOS DIVIDENDOS SOCIOS ACCIONISTAS": "611",
    "PERSONAS FISICAS ACTIVIDADES EMPRESARIALES PROFESIONALES": "612",
    "INGRESOS INTERESES": "614",
    "OBTENCION PREMIOS": "615",
    "SIN OBLIGACIONES FISCALES": "616",
    "SOCIEDADES COOPERATIVAS PRODUCCION": "620",
    "INCORPORACION FISCAL": "621",
    "ACTIVIDADES AGRICOLAS GANADERAS SILVICOLAS PESQUERAS": "622",
    "OPCIONAL GRUPOS SOCIEDADES": "623",
    "COORDINADOS": "624",
    "PLATAFORMAS TECNOLOGICAS": "625",
    "SIMPLIFICADO CONFIANZA": "626",
}


def extraer_datos_constancia_situacion_fiscal(archivo_pdf: Any) -> dict[str, str]:
    """Extrae datos de un PDF de Constancia de Situación Fiscal SAT.

    Recibe un UploadedFile de Django o cualquier objeto con ``read()``.
    Devuelve un diccionario con nombres de campos compatibles con ``ClienteForm``.
    """

    texto = _extraer_texto_pdf(archivo_pdf)
    if "CONSTANCIA DE SITUACIÓN FISCAL" not in texto.upper() and "CONSTANCIA DE SITUACION FISCAL" not in _normalizar(texto):
        raise ConstanciaFiscalPDFError(
            "El PDF no parece corresponder a una Constancia de Situación Fiscal del SAT."
        )

    rfc = _buscar_regex(texto, r"RFC:\s*([A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3})")
    curp = _buscar_regex(texto, r"CURP:\s*([A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d)")

    nombre = _buscar_entre(texto, r"Nombre\s*\(s\):", r"Primer\s*Apellido:")
    primer_apellido = _buscar_entre(texto, r"Primer\s*Apellido:", r"Segundo\s*Apellido:")
    segundo_apellido = _buscar_entre(texto, r"Segundo\s*Apellido:", r"Fecha\s*inicio\s*de\s*operaciones:")
    razon_social = _buscar_razon_social(texto)

    nombre_fiscal = razon_social or " ".join(
        parte for parte in (nombre, primer_apellido, segundo_apellido) if parte
    ).strip()

    nombre_comercial = _buscar_entre(texto, r"Nombre\s*Comercial:", r"Datos\s*del\s*domicilio\s*registrado")

    codigo_postal = _buscar_regex(texto, r"C[oó]digo\s*Postal:\s*(\d{5})")
    calle = _buscar_entre(texto, r"Nombre\s*de\s*Vialidad:", r"N[uú]mero\s*Exterior:")
    num_ext = _buscar_entre(texto, r"N[uú]mero\s*Exterior:", r"N[uú]mero\s*Interior:")
    num_int = _buscar_entre(texto, r"N[uú]mero\s*Interior:", r"Nombre\s*de\s*la\s*Colonia:")
    colonia = _buscar_entre(texto, r"Nombre\s*de\s*la\s*Colonia:", r"Nombre\s*de\s*la\s*Localidad:")
    localidad = _buscar_entre(
        texto,
        r"Nombre\s*de\s*la\s*Localidad:",
        r"Nombre\s*del\s*Municipio\s*o?\s*Demarcaci[oó]n\s*Territorial:",
    )
    municipio = _buscar_entre(
        texto,
        r"Nombre\s*del\s*Municipio\s*o?\s*Demarcaci[oó]n\s*Territorial:",
        r"Nombre\s*de\s*la\s*Entidad\s*Federativa:",
    )
    estado = _buscar_entre(texto, r"Nombre\s*de\s*la\s*Entidad\s*Federativa:", r"Entre\s*Calle:")
    entre_calle = _buscar_entre(texto, r"Entre\s*Calle:", r"Y\s*Calle:")
    y_calle = _buscar_entre(texto, r"Y\s*Calle:", r"Actividades\s*Econ[oó]micas:")

    regimenes_texto = _buscar_regimenes(texto)
    regimenes_codigos = _mapear_regimenes_fiscales(regimenes_texto)
    regimen_fiscal = regimen_fiscal_a_json(regimenes_codigos) if regimenes_codigos else ""

    datos = {
        "tipo_persona": "FISICA" if len(rfc or "") == 13 else "MORAL" if len(rfc or "") == 12 else "",
        "rfc": rfc,
        "nombre_fiscal": nombre_fiscal,
        "nombre_comercial": nombre_comercial or nombre_fiscal,
        "regimen_fiscal": regimen_fiscal,
        "domicilio_fiscal_cp": codigo_postal,
        "calle": calle,
        "num_ext": num_ext,
        "num_int": num_int,
        "colonia": colonia,
        "localidad": localidad,
        "municipio": municipio,
        "estado": estado,
        "pais": "MÉXICO" if codigo_postal or estado else "",
        "cp": codigo_postal,
        "referencias": _referencias(entre_calle, y_calle),
    }

    if regimenes_codigos:
        datos["regimenes_fiscales_codigos"] = regimenes_codigos
        datos["regimenes_fiscales_texto"] = regimenes_texto

    # CURP no existe en el modelo Cliente; queda fuera intencionalmente.
    if curp:
        datos["curp_extraida"] = curp

    return {campo: valor for campo, valor in datos.items() if valor}


def _extraer_texto_pdf(archivo_pdf: Any) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - depende del ambiente de despliegue
        raise ConstanciaFiscalPDFError(
            "No está instalada la dependencia pypdf. Ejecuta: pip install pypdf"
        ) from exc

    try:
        if hasattr(archivo_pdf, "seek"):
            archivo_pdf.seek(0)
        contenido = archivo_pdf.read()
        if hasattr(archivo_pdf, "seek"):
            archivo_pdf.seek(0)

        reader = PdfReader(io.BytesIO(contenido))
        texto_paginas = [(page.extract_text() or "") for page in reader.pages]
        texto = "\n".join(texto_paginas)
    except Exception as exc:  # pypdf usa varias excepciones internas según el daño del archivo
        raise ConstanciaFiscalPDFError(
            "No fue posible leer el PDF. Verifica que sea un archivo PDF válido y que no esté protegido."
        ) from exc

    if not texto.strip():
        raise ConstanciaFiscalPDFError(
            "No se encontró texto seleccionable dentro del PDF. La lectura automática no soporta constancias escaneadas como imagen."
        )

    return texto


def _buscar_regex(texto: str, patron: str) -> str:
    match = re.search(patron, texto, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return _limpiar_valor(match.group(1))


def _buscar_entre(texto: str, patron_inicio: str, patron_fin: str) -> str:
    patron = rf"{patron_inicio}\s*(.*?)\s*(?={patron_fin})"
    return _buscar_regex(texto, patron)


def _buscar_razon_social(texto: str) -> str:
    posibles_patrones = [
        (
            r"Denominaci[oó]n\s*/?\s*Raz[oó]n\s*Social:",
            r"(?:R[eé]gimen\s*Capital|Fecha\s*inicio\s*de\s*operaciones|Nombre\s*Comercial:)",
        ),
        (
            r"Nombre,?\s*denominaci[oó]n\s*o\s*raz[oó]n\s*social",
            r"(?:idCIF|Datos\s*de\s*Identificaci[oó]n)",
        ),
    ]
    for inicio, fin in posibles_patrones:
        valor = _buscar_entre(texto, inicio, fin)
        if valor and not re.search(r"Registro\s*Federal\s*de\s*Contribuyentes", valor, re.IGNORECASE):
            return valor
    return ""


def _buscar_regimenes(texto: str) -> list[str]:
    """Extrae todos los regímenes de la tabla Regímenes de la CSF."""
    match = re.search(
        r"Reg[ií]menes:\s*(.*?)\s*(?=Obligaciones:)",
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        regimen = _buscar_regimen(texto)
        return [regimen] if regimen else []

    bloque_original = match.group(1)
    bloque = _limpiar_valor(bloque_original)
    bloque = re.sub(
        r"R[eé]gimen\s*Fecha\s*Inicio\s*Fecha\s*Fin",
        " ",
        bloque,
        flags=re.IGNORECASE,
    )

    encontrados: list[tuple[int, str]] = []
    bloque_norm = _normalizar(bloque)

    # Primero buscar contra el catálogo SAT conocido. Es más confiable que partir
    # por fechas cuando pypdf une renglones de tablas con saltos imprecisos.
    for _codigo, etiqueta in REGIMEN_FISCAL_CHOICES:
        etiqueta_limpia = etiqueta.split(" - ", 1)[-1]
        etiqueta_norm = _normalizar(etiqueta_limpia)
        posicion = bloque_norm.find(etiqueta_norm)
        if posicion >= 0:
            encontrados.append((posicion, etiqueta_limpia))

    for texto_base in REGIMENES_ESPECIALES.keys():
        texto_norm = _normalizar(texto_base)
        palabras = [palabra for palabra in texto_norm.split() if len(palabra) > 2]
        if not palabras or not all(palabra in bloque_norm for palabra in palabras):
            continue
        posiciones = [bloque_norm.find(palabra) for palabra in palabras if bloque_norm.find(palabra) >= 0]
        posicion = min(posiciones) if posiciones else 999999
        encontrados.append((posicion, texto_base))

    if encontrados:
        unicos: list[str] = []
        vistos: set[str] = set()
        for _posicion, regimen in sorted(encontrados, key=lambda item: item[0]):
            codigo = _mapear_regimen_fiscal(regimen)
            if codigo and codigo not in vistos:
                vistos.add(codigo)
                unicos.append(_limpiar_valor(regimen))
        return unicos

    # Fallback: quitar fechas y regresar fragmentos con texto.
    bloque_sin_fechas = re.sub(r"\d{2}/\d{2}/\d{4}", "|", bloque)
    candidatos = [
        _limpiar_valor(parte)
        for parte in bloque_sin_fechas.split("|")
        if _limpiar_valor(parte)
    ]
    return [c for c in candidatos if not re.fullmatch(r"Fecha\s*Inicio|Fecha\s*Fin|R[eé]gimen", c, re.IGNORECASE)]


def _buscar_regimen(texto: str) -> str:
    """Compatibilidad: devuelve el primer régimen encontrado."""
    valor = _buscar_entre(
        texto,
        r"Reg[ií]menes:\s*R[eé]gimen\s*Fecha\s*Inicio\s*Fecha\s*Fin",
        r"\d{2}/\d{2}/\d{4}",
    )
    if valor:
        return valor

    match = re.search(
        r"Reg[ií]menes:\s*(.*?)\s*(?=Obligaciones:)", texto, re.IGNORECASE | re.DOTALL
    )
    if not match:
        return ""
    bloque = _limpiar_valor(match.group(1))
    bloque = re.sub(r"R[eé]gimen\s*Fecha\s*Inicio\s*Fecha\s*Fin", "", bloque, flags=re.IGNORECASE).strip()
    bloque = re.sub(r"\d{2}/\d{2}/\d{4}.*$", "", bloque).strip()
    return _limpiar_valor(bloque)


def _mapear_regimenes_fiscales(regimenes_texto: list[str]) -> list[str]:
    codigos = []
    for regimen_texto in regimenes_texto:
        codigo = _mapear_regimen_fiscal(regimen_texto)
        if codigo:
            codigos.append(codigo)
    return codigos_regimenes_fiscales(codigos)


def _mapear_regimen_fiscal(regimen_texto: str) -> str:
    if not regimen_texto:
        return ""

    regimen_norm = _normalizar(regimen_texto)
    regimen_norm = _quitar_prefijos_regimen(regimen_norm)

    for clave, etiqueta in REGIMEN_FISCAL_CHOICES:
        etiqueta_sin_clave = etiqueta.split(" - ", 1)[-1]
        etiqueta_norm = _quitar_prefijos_regimen(_normalizar(etiqueta_sin_clave))
        if etiqueta_norm and (etiqueta_norm in regimen_norm or regimen_norm in etiqueta_norm):
            return clave

    for texto_base, clave in REGIMENES_ESPECIALES.items():
        texto_norm = _normalizar(texto_base)
        palabras = [palabra for palabra in texto_norm.split() if len(palabra) > 2]
        if palabras and all(palabra in regimen_norm for palabra in palabras):
            return clave

    return ""


def _referencias(entre_calle: str, y_calle: str) -> str:
    referencias = []
    if entre_calle:
        referencias.append(f"Entre calle: {entre_calle}")
    if y_calle:
        referencias.append(f"Y calle: {y_calle}")
    return " | ".join(referencias)


def _limpiar_valor(valor: str) -> str:
    valor = re.sub(r"Página\s*\[\d+\]\s*de\s*\[\d+\]", " ", valor or "", flags=re.IGNORECASE)
    valor = re.sub(r"\s+", " ", valor).strip(" :-\t\r\n")
    if valor.upper() in {"N/A", "NA", "NULL", "NINGUNO"}:
        return ""
    return valor


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^A-Z0-9Ñ&]+", " ", texto.upper())
    return re.sub(r"\s+", " ", texto).strip()


def _quitar_prefijos_regimen(texto: str) -> str:
    texto = re.sub(r"\bREGIMEN\b", " ", texto)
    texto = re.sub(r"\b(DE|DEL|DE LOS|DE LAS|LAS|LOS|LA|EL)\b", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()
