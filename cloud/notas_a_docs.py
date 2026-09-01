"""
Prepara la muestra de notas de bitácora que el caso describe viviendo en
"archivos google docs" — hoy solo existen como filas de `stg_bitacora` (que a
su vez viene de `gs_desarrollo_bitacora.xlsx` / Sheets).

No escribe en Drive: una service account **sin Google Workspace detrás no
tiene cuota de almacenamiento propia** y no puede ser dueña de ningún
archivo, ni siquiera un Doc nativo (verificado en la corrida real: Drive
respondió `403 storageQuotaExceeded` al intentar crear el primer Doc). La
alternativa sin ese problema es que Alfonso sea el dueño de los Docs —su
cuota sí existe— y la SA solo los lea, exactamente el mismo modelo de
permisos que ya funciona para `fuentes/` en F2 (Lector, `drive.readonly`).

Este script genera un único archivo Markdown con las N notas, cada una lista
para copiar y pegar en un Doc nuevo dentro de `buk-caso-practico/notas/`
(hermana de `fuentes/`, compartida con la SA como Lector). `leer_docs.py`
después no depende del título que le pongas a cada Doc — solo lee el
contenido de lo que encuentre en esa carpeta.

Uso:
    uv run --project cloud python cloud/notas_a_docs.py --n 20
"""

from __future__ import annotations

import argparse
import pathlib

import config

SALIDA = pathlib.Path(__file__).parent.parent / "data" / "out" / "notas_para_docs.md"


def muestra(n: int):
    cli = config.cliente()
    sql = f"""
        SELECT employee_id, fecha, autor_hrbp, tipo_instancia, nota
        FROM `{config.DATASET_ID}.stg_bitacora`
        ORDER BY employee_id, fecha
        LIMIT {int(n)}
    """
    return list(cli.query(sql, location=config.REGION).result())


def escribir(filas, destino: pathlib.Path) -> None:
    bloques = [
        "# Notas para copiar a Google Docs\n",
        f"{len(filas)} notas · una por Doc, dentro de "
        "`buk-caso-practico/notas/` (compartida con la SA como Lector).\n",
        "Para cada bloque: Doc nuevo → pega el título como nombre del "
        "archivo → pega el texto como contenido.\n",
    ]
    for i, fila in enumerate(filas, start=1):
        titulo = f"{fila.employee_id} · {fila.fecha.isoformat()} · {fila.tipo_instancia}"
        bloques.append(f"\n---\n\n## {i}. {titulo}\n\n{fila.nota}\n")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("".join(bloques), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=20)
    args = ap.parse_args()

    filas = muestra(args.n)
    escribir(filas, SALIDA)
    print(f"{len(filas)} notas escritas en {SALIDA.relative_to(SALIDA.parent.parent.parent)}")
    print("Siguiente paso: crear buk-caso-practico/notas/ en Drive, compartirla con")
    print(f"   {config.SERVICE_ACCOUNT}")
    print("como Lector, y copiar cada bloque del archivo a un Doc nuevo dentro.")


if __name__ == "__main__":
    main()
