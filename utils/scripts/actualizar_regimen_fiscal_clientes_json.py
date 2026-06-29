#!/usr/bin/env python3
"""Actualiza Cliente.regimen_fiscal al nuevo formato JSON.

Uso recomendado en producción:

    python utils/scripts/actualizar_regimen_fiscal_clientes_json.py --dry-run
    python utils/scripts/actualizar_regimen_fiscal_clientes_json.py --yes

Convierte valores legados como:
    612

a:
    [{"codigo":"612","descripcion":"Personas Físicas con Actividades Empresariales y Profesionales"}]

Los clientes sin régimen quedan como [] para que todos manejen la misma estructura.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from catalogos.models import Cliente  # noqa: E402
from catalogos.services.regimenes_fiscales import regimen_fiscal_a_json  # noqa: E402


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    yes = "--yes" in sys.argv or "-y" in sys.argv

    total = Cliente.objects.count()
    cambios: list[tuple[int, str, str, str]] = []

    for cliente in Cliente.objects.only("id", "rfc", "nombre_fiscal", "regimen_fiscal").iterator():
        original = cliente.regimen_fiscal or ""
        nuevo = regimen_fiscal_a_json(original)
        if original != nuevo:
            cambios.append((cliente.id, cliente.rfc or "", original, nuevo))

    print("Actualización de régimen fiscal de clientes a formato JSON")
    print(f"Clientes revisados: {total}")
    print(f"Clientes por actualizar: {len(cambios)}")

    if cambios:
        print("\nPrimeros cambios detectados:")
        for cliente_id, rfc, original, nuevo in cambios[:20]:
            print(f"  Cliente #{cliente_id} {rfc}: {original!r} -> {nuevo!r}")
        if len(cambios) > 20:
            print(f"  ... {len(cambios) - 20} cambios adicionales")

    if dry_run:
        print("\nModo dry-run: no se actualizó ningún registro.")
        return 0

    if cambios and not yes:
        respuesta = input("\n¿Aplicar actualización? Escribe SI para continuar: ").strip().upper()
        if respuesta != "SI":
            print("Operación cancelada. No se actualizó ningún registro.")
            return 1

    actualizados = 0
    for cliente_id, _rfc, _original, nuevo in cambios:
        Cliente.objects.filter(pk=cliente_id).update(regimen_fiscal=nuevo)
        actualizados += 1

    print(f"\nRegistros actualizados: {actualizados}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
