"""DEMO 2 — el modelo nunca ve un nombre.

Toma una nota real, la redacta con el mismo scrubber que corre en producción y
muestra el antes, el después y lo que queda guardado en la caché.

Dos orígenes, el mismo scrubber:

    # (a) desde el XLSX local — sin red, sin credenciales
    uv run python demo_scrubber.py
    uv run python demo_scrubber.py --id BUK10089

    # (b) desde el Google Doc real, leído en vivo por Drive + Docs API
    uv run --project cloud python demo_scrubber.py --doc
    uv run --project cloud python demo_scrubber.py --doc --nota 18

El modo (b) es el que permite editar el Doc en el navegador y volver a correr:
el texto cambia, la redacción cambia y el hash cambia con él.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src" / "llm"))

from provider import _archivo_cache, _hash  # noqa: E402
from scrubber import redactar  # noqa: E402

FUENTE_XLSX = RAIZ / "data" / "raw" / "gs_desarrollo_bitacora.xlsx"

# Hay dos carpetas llamadas `notas` visibles para la SA y leer_docs se niega a
# adivinar. Esta es la que tiene los 19 Docs.
CARPETA_NOTAS = "1-xWAMSDRVO33iR426WOp-KNzWAagpFiF"

# El Doc con el que se ensayó: ya menciona a una persona del directorio.
NOTA_POR_DEFECTO = "7"


def _mostrar(titulo: str, original: str) -> None:
    limpia = redactar(original)
    h = _hash(limpia)
    cache = _archivo_cache(h)

    print(f"\n{titulo}")
    print("\n\033[1mANTES — lo que dice el Doc\033[0m")
    print(original)
    print("\n\033[1mDESPUÉS — lo único que sale del perímetro\033[0m")
    print(limpia)
    print(f"\n\033[1mLO QUE QUEDA GUARDADO — data/cache/llm/{h}.json\033[0m")
    if cache.exists():
        guardado = json.loads(cache.read_text(encoding="utf-8"))
        print("estado: EN CACHÉ — esta nota no se vuelve a mandar al modelo")
        print("claves:", ", ".join(guardado))
        print("texto_scrubbed:", guardado["texto_scrubbed"][:120], "…")
        print("citas_respaldo:", guardado["citas_respaldo"])
    else:
        print("estado: SIN CACHÉ — el texto cambió, así que el hash cambió:")
        print("        esta nota sí sería una llamada nueva al modelo.")
    print("\nEl nombre del archivo es el hash del texto de ABAJO, no el de arriba:")
    print("no puede filtrar lo que el scrubber quitó.")


def desde_doc(nota: str, carpeta_id: str) -> None:
    """Lee el Doc en vivo desde Drive. Requiere credenciales (ADC)."""
    sys.path.insert(0, str(RAIZ / "cloud"))
    import leer_docs  # noqa: PLC0415

    drive, docs = leer_docs._servicios()
    archivos = leer_docs.listar(drive, carpeta_id)
    elegidos = [a for a in archivos if a["name"].split(".")[0].strip() == nota]
    if not elegidos:
        elegidos = [a for a in archivos if nota.lower() in a["name"].lower()]
    if not elegidos:
        print(f"Ningún Doc coincide con «{nota}». Los que hay:")
        for a in sorted(archivos, key=lambda x: int(x["name"].split(".")[0])):
            print("  ·", a["name"])
        return

    archivo = elegidos[0]
    _mostrar(f"Doc en vivo · {archivo['name']}", leer_docs.texto_plano(docs, archivo["id"]))


def desde_xlsx(employee_id: str | None) -> None:
    """Lee el XLSX local. Sin red y sin credenciales: es el plan de respaldo."""
    import pandas as pd  # noqa: PLC0415

    notas = pd.read_excel(FUENTE_XLSX, sheet_name="Bitácora").dropna(subset=["nota"])
    if employee_id:
        notas = notas[notas["employee_id"].astype(str).str.strip() == employee_id]

    for _, fila in notas.iterrows():
        original = str(fila["nota"])
        limpia = redactar(original)
        # Buscamos una que muestre las dos redacciones a la vez, persona y cliente,
        # y que además esté en la caché: así los tres pasos hablan de la misma nota.
        if "[PERSONA_" not in limpia or "[CLIENTE]" not in limpia:
            continue
        if not employee_id and not _archivo_cache(_hash(limpia)).exists():
            continue
        titulo = f"{fila['employee_id']} · {str(fila['fecha'])[:10]} · {fila['tipo_instancia']}"
        _mostrar(titulo, original)
        return

    print("No se encontró una nota con nombre y cliente para ese filtro.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--doc", action="store_true", help="leer el Google Doc real, en vivo")
    ap.add_argument("--nota", default=NOTA_POR_DEFECTO, help="número o parte del nombre del Doc")
    ap.add_argument("--carpeta-id", default=CARPETA_NOTAS)
    ap.add_argument("--id", dest="employee_id", default=None, help="employee_id (modo XLSX)")
    args = ap.parse_args()

    if args.doc:
        desde_doc(args.nota, args.carpeta_id)
    else:
        desde_xlsx(args.employee_id)


if __name__ == "__main__":
    main()
