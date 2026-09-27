"""
Lee desde Drive los Docs de `buk-caso-practico/notas/` (creados a mano por
Alfonso — ver `notas_a_docs.py`): Drive API lista la carpeta, Docs API
extrae el texto plano de cada uno.

Misma identidad y mismo permiso que F2 sobre `fuentes/`: la SA impersonada
con `drive.readonly` (`config.credenciales(impersonar=True, con_drive=True)`),
Lectora de una carpeta que Alfonso comparte a mano. Nunca Editora, nunca dueña
de nada.

El texto que sale de acá entra al pipeline de LLM **sin cambios**:
`scrubber.redactar()` -> `provider.procesar_nota()` -> `schema.validar()`,
los tres importados de `src/llm/` (los tres se encadenan dentro de
`procesar_nota()`, no se repiten acá). Lo único que cambia respecto al XLSX
es el origen del texto: un Doc en vez de una celda.

Uso:
    uv run --project cloud python cloud/leer_docs.py
    uv run --project cloud python cloud/leer_docs.py --carpeta-id <ID>
"""

from __future__ import annotations

import argparse
import sys

from googleapiclient.discovery import build

import config

MIME_DOC = "application/vnd.google-apps.document"
MIME_CARPETA = "application/vnd.google-apps.folder"

config.usar_src()
sys.path.insert(0, str(config.SRC / "llm"))
from provider import procesar_nota  # noqa: E402


def _servicios():
    creds = config.credenciales(impersonar=True, con_drive=True)
    drive = build("drive", "v3", credentials=creds)
    docs = build("docs", "v1", credentials=creds)
    return drive, docs


def carpeta_notas(drive, carpeta_id: str | None) -> str:
    """El ID de `notas/`, dado directo o encontrado por nombre entre lo compartido."""
    if carpeta_id:
        return carpeta_id
    resp = drive.files().list(
        q=f"name = 'notas' and mimeType = '{MIME_CARPETA}' and trashed = false",
        fields="files(id, name)",
        pageSize=5,
    ).execute()
    encontradas = resp.get("files", [])
    if not encontradas:
        raise RuntimeError(
            "No encontré una carpeta 'notas' compartida con la SA. Comparte "
            "buk-caso-practico/notas/ con "
            f"{config.SERVICE_ACCOUNT} como Lector, o pasa --carpeta-id."
        )
    if len(encontradas) > 1:
        raise RuntimeError(
            f"Hay {len(encontradas)} carpetas 'notas' visibles para la SA: "
            f"{[f['id'] for f in encontradas]} — pasa --carpeta-id para desambiguar."
        )
    return encontradas[0]["id"]


def listar(drive, carpeta: str) -> list[dict]:
    resp = drive.files().list(
        q=f"'{carpeta}' in parents and mimeType = '{MIME_DOC}' and trashed = false",
        fields="files(id, name)",
        pageSize=200,
    ).execute()
    return resp.get("files", [])


def texto_plano(docs, doc_id: str) -> str:
    """Concatena los `textRun` del cuerpo del documento, en orden."""
    documento = docs.documents().get(documentId=doc_id).execute()
    partes = []
    for elemento in documento.get("body", {}).get("content", []):
        parrafo = elemento.get("paragraph")
        if not parrafo:
            continue
        for run in parrafo.get("elements", []):
            texto = run.get("textRun", {}).get("content")
            if texto:
                partes.append(texto)
    return "".join(partes).strip()


def leer_todas(carpeta_id: str | None = None) -> dict[str, str]:
    """`{nombre_del_doc: texto_plano}` para cada nota en la carpeta."""
    drive, docs = _servicios()
    carpeta = carpeta_notas(drive, carpeta_id)
    return {a["name"]: texto_plano(docs, a["id"]) for a in listar(drive, carpeta)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--carpeta-id", default=None)
    ap.add_argument("--sin-cache", action="store_true")
    ap.add_argument("--n", type=int, default=None, help="procesar solo las primeras N")
    args = ap.parse_args()

    notas = leer_todas(args.carpeta_id)
    print(f"{len(notas)} Docs leídos desde Drive\n")

    items = list(notas.items())[: args.n] if args.n else list(notas.items())
    for nombre, texto in items:
        envoltorio = procesar_nota(texto, usar_cache=not args.sin_cache)
        print(f"· {nombre}")
        print(f"  sentimiento={envoltorio['sentimiento']} temas={envoltorio['temas']}")


if __name__ == "__main__":
    main()
