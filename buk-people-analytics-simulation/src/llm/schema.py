"""
Esquema de salida del LLM sobre notas de bitácora: JSON estricto, enum cerrado.

Por qué un enum cerrado y no texto libre: si el modelo puede inventar temas,
las categorías derivan en el tiempo y dejan de ser agregables — el mismo
argumento de gobernanza que ya sostiene `textos.TEMAS`, del que este módulo
importa la lista en vez de mantener una copia que se puede desincronizar.

Una respuesta que no valida no se corrige a mano: se reintenta una vez y, si
vuelve a fallar, se marca `no_procesado`. Nunca se completa un campo con un
valor plausible — eso sería peor que no tener el dato, porque no se distingue
de una lectura real.

La verificación más importante no la puede expresar un JSON Schema: toda cita
de respaldo tiene que aparecer, textual, en la nota que se le mostró al
modelo. Es la forma barata de detectar una alucinación sin depender de un
segundo modelo que la juzgue.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from textos import TEMAS  # noqa: E402

SENTIMIENTOS = ["positivo", "neutro", "negativo", "insuficiente"]
MAX_TEMAS = 3
MAX_CITAS = 3


class RespuestaInvalida(Exception):
    """La respuesta del modelo rompe el esquema o no se sostiene con el texto.

    No se corrige ni se completa: el llamador decide si reintenta o si marca
    la nota como `no_procesado`.
    """


def json_schema() -> dict:
    """Esquema en el formato que `response_schema` de la API de Gemini espera."""
    return {
        "type": "object",
        "properties": {
            "sentimiento": {"type": "string", "enum": SENTIMIENTOS},
            "temas": {
                "type": "array", "items": {"type": "string", "enum": TEMAS},
                "maxItems": MAX_TEMAS,
            },
            "senales": {
                "type": "array", "items": {"type": "string", "enum": TEMAS},
                "maxItems": MAX_TEMAS,
            },
            "citas_respaldo": {
                "type": "array", "items": {"type": "string"}, "maxItems": MAX_CITAS,
            },
            "confianza": {"type": "number"},
        },
        "required": ["sentimiento", "temas", "senales", "citas_respaldo", "confianza"],
    }


def validar(resp: dict, texto_scrubbed: str) -> None:
    """Verifica `resp` contra el esquema y contra el texto que la originó.

    `texto_scrubbed` es el texto redactado que efectivamente se le mostró al
    modelo — nunca el original. Verificar contra el original permitiría que
    una cita "válida" reconstruyera un nombre que el scrubber ya había
    quitado.
    """
    if not isinstance(resp, dict):
        raise RespuestaInvalida("la respuesta no es un objeto JSON")

    sentimiento = resp.get("sentimiento")
    if sentimiento not in SENTIMIENTOS:
        raise RespuestaInvalida(f"sentimiento fuera de enum: {sentimiento!r}")

    temas = resp.get("temas")
    if not isinstance(temas, list) or len(temas) > MAX_TEMAS:
        raise RespuestaInvalida(f"temas inválido: {temas!r}")
    if not set(temas) <= set(TEMAS):
        raise RespuestaInvalida(f"tema fuera de enum: {set(temas) - set(TEMAS)}")

    senales = resp.get("senales")
    if not isinstance(senales, list) or len(senales) > MAX_TEMAS:
        raise RespuestaInvalida(f"señales inválido: {senales!r}")
    if not set(senales) <= set(temas):
        raise RespuestaInvalida("una señal tiene que ser también uno de los temas")

    citas = resp.get("citas_respaldo")
    if not isinstance(citas, list) or len(citas) > MAX_CITAS:
        raise RespuestaInvalida(f"citas_respaldo inválido: {citas!r}")
    for c in citas:
        if not isinstance(c, str) or not c.strip():
            raise RespuestaInvalida("una cita vacía no es una cita")
        if c.strip() not in texto_scrubbed:
            raise RespuestaInvalida(f"cita no verificable contra la nota: {c!r}")

    confianza = resp.get("confianza")
    if isinstance(confianza, bool) or not isinstance(confianza, (int, float)):
        raise RespuestaInvalida(f"confianza no es numérica: {confianza!r}")
    if not (0.0 <= float(confianza) <= 1.0):
        raise RespuestaInvalida(f"confianza fuera de [0,1]: {confianza!r}")

    if sentimiento == "insuficiente" and (temas or senales or citas):
        raise RespuestaInvalida("insuficiente no debería traer temas, señales ni citas")
