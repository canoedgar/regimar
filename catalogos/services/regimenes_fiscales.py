"""Utilidades para manejar el campo Cliente.regimen_fiscal como JSON.

El campo se conserva con el mismo nombre para compatibilidad histórica, pero ahora
almacena una lista JSON de regímenes SAT, por ejemplo:
[
    {"codigo": "612", "descripcion": "Personas Físicas con Actividades Empresariales y Profesionales"},
    {"codigo": "626", "descripcion": "Régimen Simplificado de Confianza"}
]

Las funciones aceptan también el formato anterior ("612") para poder leer clientes
existentes antes de ejecutar el script de actualización.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

from catalogos.sat_catalogos import REGIMEN_FISCAL_CHOICES

REGIMEN_FISCAL_DICT = {
    str(codigo): etiqueta.split(" - ", 1)[-1]
    for codigo, etiqueta in REGIMEN_FISCAL_CHOICES
}
REGIMEN_FISCAL_LABEL_DICT = dict(REGIMEN_FISCAL_CHOICES)


def regimen_fiscal_a_json(valor: Any) -> str:
    """Convierte códigos, listas o JSON previo a la estructura JSON canónica."""
    return json.dumps(
        normalizar_regimenes_fiscales(valor),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def normalizar_regimenes_fiscales(valor: Any) -> list[dict[str, str]]:
    """Devuelve una lista de dicts {codigo, descripcion} sin duplicados.

    Acepta:
    - Código legado: "612"
    - CSV simple: "612,626"
    - Lista de códigos: ["612", "626"]
    - Lista de objetos: [{"codigo": "612", "descripcion": "..."}]
    - JSON texto en cualquiera de las dos formas anteriores.
    """
    codigos: list[str] = []

    if valor is None:
        return []

    if isinstance(valor, str):
        valor = valor.strip()
        if not valor:
            return []
        try:
            decodificado = json.loads(valor)
        except (TypeError, ValueError, json.JSONDecodeError):
            return _regimenes_desde_codigos(parte.strip() for parte in valor.split(","))
        # json.loads("612") produce el número 612; se atiende en la rama genérica.
        return normalizar_regimenes_fiscales(decodificado)

    if isinstance(valor, dict):
        codigo = str(valor.get("codigo") or valor.get("clave") or valor.get("regimen") or "").strip()
        if codigo:
            codigos.append(codigo)
    elif isinstance(valor, (list, tuple, set)):
        for item in valor:
            for regimen in normalizar_regimenes_fiscales(item):
                codigos.append(regimen["codigo"])
    else:
        texto = str(valor or "").strip()
        if texto:
            codigos.extend(parte.strip() for parte in texto.split(","))

    return _regimenes_desde_codigos(codigos)


def _regimenes_desde_codigos(codigos: Iterable[Any]) -> list[dict[str, str]]:
    vistos: set[str] = set()
    regimenes: list[dict[str, str]] = []
    for codigo_raw in codigos:
        codigo = str(codigo_raw or "").strip()
        if not codigo:
            continue
        # Evita que una cadena CSV haya pasado como un solo elemento.
        if "," in codigo:
            for regimen in _regimenes_desde_codigos(codigo.split(",")):
                if regimen["codigo"] not in vistos:
                    vistos.add(regimen["codigo"])
                    regimenes.append(regimen)
            continue
        if codigo not in REGIMEN_FISCAL_DICT or codigo in vistos:
            continue
        vistos.add(codigo)
        regimenes.append({
            "codigo": codigo,
            "descripcion": REGIMEN_FISCAL_DICT[codigo],
        })
    return regimenes


def codigos_regimenes_fiscales(valor: Any) -> list[str]:
    """Extrae únicamente los códigos SAT del valor guardado."""
    return [regimen["codigo"] for regimen in normalizar_regimenes_fiscales(valor)]


def codigo_regimen_fiscal_principal(valor: Any) -> str:
    """Regresa el primer régimen registrado, útil para compatibilidad con flujos antiguos."""
    codigos = codigos_regimenes_fiscales(valor)
    return codigos[0] if codigos else ""


def display_regimenes_fiscales(valor: Any, incluir_codigo: bool = True) -> str:
    """Representación legible para listados y admin."""
    regimenes = normalizar_regimenes_fiscales(valor)
    if not regimenes:
        return ""
    if incluir_codigo:
        return ", ".join(f"{r['codigo']} - {r['descripcion']}" for r in regimenes)
    return ", ".join(r["descripcion"] for r in regimenes)


def etiqueta_regimen_fiscal(codigo: str) -> str:
    """Etiqueta completa del catálogo SAT para un código."""
    return REGIMEN_FISCAL_LABEL_DICT.get(str(codigo or "").strip(), str(codigo or "").strip())
