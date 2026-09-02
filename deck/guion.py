"""Guion del orador, extraído de deck/plantilla.html.

Existe por la misma razón que `construir.py` hornea las cifras en vez de
transcribirlas: GUION.md era una copia a mano y se quedó atrás tres veces.
Las notas viven en los `<div class="notas-fuente">` de la plantilla — acá solo
se pasan a Markdown para tenerlas en una pantalla que no se comparte.

    uv run python deck/guion.py
"""

from __future__ import annotations

import html
import json
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parent.parent
PLANTILLA = RAIZ / "deck" / "plantilla.html"
DATOS = RAIZ / "deck" / "datos.json"
SALIDA = RAIZ / "GUION.md"

CABECERA = """# Guion del orador — copia de respaldo, fuera del deck

Generado por `deck/guion.py` desde `deck/plantilla.html`. No editar a mano: se
regenera. Abrir en una ventana o pantalla que NO se comparte durante la llamada;
no depende de las teclas `N`/`C` del deck compartido.
"""


def _fmt(v) -> str:
    """Mismo formato que `fmt()` en la plantilla: es-CL, un decimal si no es entero."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, int):
        return f"{v:,}".replace(",", ".")
    return f"{v:,.1f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _resolver(fragmento: str, datos: dict) -> str:
    """Rellena los data-d de las notas con el mismo dato horneado que ve la lámina."""
    def uno(m: re.Match) -> str:
        valor = datos
        for k in m.group(1).split("."):
            if isinstance(valor, list):
                valor = len(valor) if k == "length" else valor[int(k)]
            elif isinstance(valor, dict):
                valor = valor.get(k)
            else:
                return m.group(0)
            if valor is None:
                return m.group(0)
        return f"<span>{_fmt(valor)}</span>"
    return re.sub(r"<(?:b|span)[^>]*data-d=\"([^\"]+)\"[^>]*>\s*</(?:b|span)>", uno, fragmento)


def _texto(fragmento: str) -> str:
    """HTML de un <p> a texto plano, conservando el énfasis como Markdown."""
    t = re.sub(r"<span class=\"min\">(.*?)</span>", r"\1", fragmento, flags=re.S)
    t = re.sub(r"</?(?:b|strong)>", "**", t, flags=re.S)
    t = re.sub(r"</?(?:i|em)>", "*", t, flags=re.S)
    t = re.sub(r"<[^>]+>", "", t, flags=re.S)
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return re.sub(r"\*\*\s*\*\*", "", t)


def guion() -> str:
    fuente = PLANTILLA.read_text(encoding="utf-8")
    datos = json.loads(DATOS.read_text(encoding="utf-8"))
    fuente = _resolver(fuente, datos)
    partes = [CABECERA]

    secciones = re.findall(
        r"<section class=\"slide\"[^>]*data-titulo=\"([^\"]+)\"[^>]*>(.*?)</section>",
        fuente, flags=re.S)
    for i, (titulo, cuerpo) in enumerate(secciones, start=1):
        notas = re.search(r"<div class=\"notas-fuente\">(.*?)</div>\s*</section>",
                          cuerpo + "</section>", flags=re.S)
        partes.append(f"\n---\n\n## Slide {i} · {titulo}\n")
        if not notas:
            partes.append("_(sin notas en la plantilla)_\n")
            continue
        for clase, p in re.findall(r"<p(?: class=\"(\w+)\")?>(.*?)</p>",
                                   notas.group(1), flags=re.S):
            linea = _texto(p)
            if clase != "preg":
                partes.append(f"{linea}\n")
            elif linea.startswith("**"):   # la nota ya trae su propio titular en negrita
                partes.append(f"**P · {linea[2:]}\n")
            else:
                partes.append(f"**P:** {linea}\n")

    # El recorrido de la salida a la nube no es una slide: vive en el overlay `C`.
    nube = re.search(r"<div id=\"nube\".*?<ol[^>]*>(.*?)</ol>", fuente, flags=re.S)
    if nube:
        partes.append("\n---\n\n## Salida a la nube (tecla `C`, entre S3 y S4)\n")
        for li in re.findall(r"<li>(.*?)</li>", nube.group(1), flags=re.S):
            partes.append(f"- {_texto(li)}\n")

    return "\n".join(partes)


if __name__ == "__main__":
    SALIDA.write_text(guion(), encoding="utf-8")
    n = len(SALIDA.read_text(encoding="utf-8").splitlines())
    print(f"→ {SALIDA.relative_to(RAIZ)} ({n} líneas) desde deck/plantilla.html")
