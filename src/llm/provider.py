"""
Adaptador de LLM: la única pieza de este módulo que sale a internet.

`procesar_nota()` es la interfaz completa: redacta, revisa la caché, llama al
modelo si hace falta, valida la respuesta contra `schema.py`, reintenta una
vez si no valida, y si vuelve a fallar devuelve `no_procesado` en vez de
inventar. Quien llama nunca ve una excepción de red ni un JSON a medio parsear.

La caché se indexa por el hash de la nota YA REDACTADA, nunca del original: el
nombre del archivo de caché no puede filtrar lo que el scrubber quitó, y la
demo corre completa sin red si `data/cache/llm/` ya tiene las notas que se van
a mostrar en vivo.

Por qué Gemini acá y Claude en la recomendación de producción: el adaptador no
se casa con un proveedor — `MODELO` y las credenciales son lo único que
cambia. En producción la recomendación es Claude vía Vertex AI Model Garden:
mismo cliente (`google-genai` con `vertexai=True` en vez de `api_key`), el
dato nunca sale del perímetro contractual de GCP, sin entrenamiento sobre el
input.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import sys

from dotenv import load_dotenv
from google import genai
from google.genai import types

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from schema import RespuestaInvalida, json_schema, validar  # noqa: E402
from scrubber import redactar  # noqa: E402

RAIZ = pathlib.Path(__file__).parent.parent.parent
load_dotenv(RAIZ / ".env")

CACHE = RAIZ / "data" / "cache" / "llm"
# Configurable por env var para no tener que tocar código si el nombre del
# modelo cambia entre hoy y la demo.
MODELO = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
VERSION_PROMPT = "v1"

PROMPT_SISTEMA = """Eres un analista de People Analytics leyendo UNA nota de \
seguimiento (bitácora) de un Happiness Manager sobre un colaborador de Buk.

Tu única tarea es extraer, del texto que se te entrega, el sentimiento \
general y hasta 3 temas mencionados explícitamente, usando SOLO la lista \
cerrada de temas del esquema. Nunca uses un tema fuera de esa lista.

Reglas estrictas:
- No infieras salud, situación familiar, orientación sexual, religión, \
nacionalidad, ni intención de renuncia. Ninguna de esas categorías existe en \
el esquema y ninguna debe aparecer en tu respuesta, en ninguna forma.
- No emitas ninguna recomendación sobre la persona ni sobre qué debería \
hacer el Happiness Manager.
- "senales" es el subconjunto de "temas" que se describe en tono negativo: \
un tema puede estar presente sin ser una señal de riesgo.
- Cada cita en "citas_respaldo" debe ser una copia TEXTUAL, palabra por \
palabra, de un fragmento de la nota. Nunca la parafrasees ni la inventes.
- Si el texto no trae evidencia clara para evaluar sentimiento o temas, \
responde sentimiento="insuficiente" con temas, senales y citas_respaldo \
vacíos. Es preferible declarar que no hay evidencia a forzar una lectura.
- Los nombres, clientes y montos ya vienen redactados como [PERSONA_N], \
[CLIENTE] y [MONTO]. No intentes reconstruirlos ni comentarlos.
"""


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:24]


def _archivo_cache(h: str) -> pathlib.Path:
    return CACHE / f"{h}.json"


def _leer_cache(h: str) -> dict | None:
    ruta = _archivo_cache(h)
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def _escribir_cache(h: str, envoltorio: dict) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    _archivo_cache(h).write_text(
        json.dumps(envoltorio, ensure_ascii=False, indent=2), encoding="utf-8"
    )


_cliente: genai.Client | None = None

# Por defecto, modo `api_key` (demo local, sin cambios). En "vertex", el
# mismo cliente `google-genai` habla con Vertex AI (`vertexai=True`) en vez
# de la API pública — el dato no sale del perímetro GCP. Se activa con
# GEMINI_BACKEND=vertex; si no se define, el comportamiento de hoy no cambia.
BACKEND = os.environ.get("GEMINI_BACKEND", "api_key")
VERTEX_PROJECT = os.environ.get("GEMINI_VERTEX_PROJECT") or os.environ.get("BQ_PROYECTO")
VERTEX_LOCATION = os.environ.get("GEMINI_VERTEX_LOCATION", "us-central1")


def _cliente_gemini() -> genai.Client:
    global _cliente
    if _cliente is None:
        if BACKEND == "vertex":
            if not VERTEX_PROJECT:
                raise RuntimeError(
                    "GEMINI_BACKEND=vertex requiere GEMINI_VERTEX_PROJECT "
                    "(o BQ_PROYECTO) en el ambiente"
                )
            _cliente = genai.Client(
                vertexai=True, project=VERTEX_PROJECT, location=VERTEX_LOCATION,
            )
        else:
            clave = os.environ.get("GEMINI_API_KEY")
            if not clave:
                raise RuntimeError("GEMINI_API_KEY no está en el ambiente (revisa .env)")
            _cliente = genai.Client(api_key=clave)
    return _cliente


def _llamar_modelo(texto_scrubbed: str) -> dict:
    respuesta = _cliente_gemini().models.generate_content(
        model=MODELO,
        contents=texto_scrubbed,
        config=types.GenerateContentConfig(
            system_instruction=PROMPT_SISTEMA,
            response_mime_type="application/json",
            response_json_schema=json_schema(),
            temperature=0.0,
        ),
    )
    return json.loads(respuesta.text)


def _procesar_sin_cache(texto_scrubbed: str) -> dict:
    """Llama al modelo y valida. Un solo reintento ante respuesta inválida."""
    ultimo_error = "sin intentos"
    for _ in range(2):
        try:
            resp = _llamar_modelo(texto_scrubbed)
            validar(resp, texto_scrubbed)
            return resp
        except (RespuestaInvalida, json.JSONDecodeError, KeyError) as e:
            ultimo_error = str(e)
    return {
        "sentimiento": "no_procesado", "temas": [], "senales": [],
        "citas_respaldo": [], "confianza": 0.0, "error": ultimo_error,
    }


def procesar_nota(texto: str, usar_cache: bool = True) -> dict:
    """Procesa una nota de bitácora de punta a punta. Devuelve el envoltorio completo.

    El envoltorio trae, además de la respuesta del modelo, la trazabilidad que
    pide la gobernanza del eje 2: qué modelo, qué versión de prompt, cuándo, y
    el hash de la nota redactada — nunca el texto original.
    """
    texto_scrubbed = redactar(texto)
    h = _hash(texto_scrubbed)

    if usar_cache:
        cacheado = _leer_cache(h)
        if cacheado is not None:
            return cacheado

    resp = _procesar_sin_cache(texto_scrubbed)
    envoltorio = {
        "hash_nota": h,
        "modelo": MODELO,
        "version_prompt": VERSION_PROMPT,
        "procesado_en": dt.datetime.now(dt.timezone.utc).isoformat(),
        "texto_scrubbed": texto_scrubbed,
        **resp,
    }
    if usar_cache:
        _escribir_cache(h, envoltorio)
    return envoltorio
