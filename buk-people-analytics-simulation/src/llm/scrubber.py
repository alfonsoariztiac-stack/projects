"""
Redacción determinista de PII antes de que el texto salga hacia el LLM.

Determinista y no estadística, a propósito: un extractor de entidades puede
fallar en silencio y dejar pasar un nombre; hacer el match contra una lista
de nombres reales conocidos —el propio directorio de Buk— falla ruidosamente
si la lista está desactualizada, no en silencio. No es la solución de
producción (ahí corresponde Cloud DLP, ver `provider.py`), es la versión que
se puede auditar leyendo este archivo entero en un minuto.

La lista de nombres sale del directorio (`bq_directorio_personas.csv`), no
de la lista fija de 20 nombres de `textos.py`: una nota puede mencionar a
cualquier colaborador real, no solo a los que usa el generador sintético
para poblar el texto de ejemplo. En producción esta lista se reconstruye en
cada corrida desde el directorio vigente; acá se cachea una vez por proceso.
"""

from __future__ import annotations

import collections
import pathlib
import re
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from textos import CLIENTES_EN_TEXTO  # noqa: E402

RAIZ = pathlib.Path(__file__).parent.parent.parent
DIRECTORIO = RAIZ / "data" / "raw" / "bq_directorio_personas.csv"

_MONTO = re.compile(
    r"\$\s?\d[\d.,]*|\b\d[\d.,]*\s?(?:mil|millones|CLP|PEN|COP|MXN|BRL|USD)\b",
    re.IGNORECASE,
)
_ID_BUKER = re.compile(r"\bBUK\d{5}\b")
_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")

# Partículas y títulos que aparecen dentro de nombres compuestos del
# directorio real ("Ana del Carmen Soto", "Dr. Luis Pérez") pero que no son,
# por sí solos, un nombre de pila ni un apellido. Sin este filtro, partir
# cada nombre por espacio y aceptar cualquier token de 3+ letras deja pasar
# "del" como si fuera una persona — y "del" es una preposición, no un dato
# personal.
_PARTICULAS = frozenset({
    "del", "das", "de", "la", "las", "los", "da", "do", "dos",
    "van", "von", "mac", "san", "y", "e",
})
_TITULOS = frozenset({
    "dr", "sr", "sra", "srta", "lic", "ing", "phd", "md", "don",
    "iii", "ii", "iv", "jr",
})

_patron_nombres_cache: re.Pattern | None = None
_patron_clientes_cache: re.Pattern | None = None


class ListaDeNombresInvalida(Exception):
    """El directorio dejó pasar una partícula o un título como nombre propio.

    Defensa en profundidad: `_tokens_directorio()` ya filtra este ruido antes
    de aceptar un token, así que esto solo debería dispararse si ese filtro
    se rompe en un cambio futuro — y en ese caso preferimos fallar ruidosamente
    acá, no volver a redactar "del" 14.104 veces en silencio.
    """


class TasaRedaccionSospechosa(Exception):
    """Un solo token concentra una fracción anómala de las redacciones de la corrida."""


def _es_ruido(parte: str) -> bool:
    p = parte.lower().rstrip(".")
    return p in _PARTICULAS or p in _TITULOS


def _tokens_directorio() -> tuple[set[str], set[str]]:
    """Nombres completos y tokens sueltos (3+ letras, con mayúscula inicial) del directorio.

    Se devuelven ambos porque el match debe intentar el nombre completo antes
    que un token suelto (ver `_patron_nombres()`): así "del" nunca puede
    aparecer como match por sí solo, solo como parte de "Ana del Carmen Soto"
    ya redactado como unidad.
    """
    if not DIRECTORIO.exists():
        return set(), set()
    df = pd.read_csv(DIRECTORIO, usecols=["nombre"])
    completos: set[str] = set()
    tokens: set[str] = set()
    for nombre in df["nombre"].dropna():
        nombre = str(nombre).strip()
        if nombre:
            completos.add(nombre)
        for parte in nombre.split():
            if len(parte) >= 3 and parte[:1].isupper() and not _es_ruido(parte):
                tokens.add(parte)

    coladas = {t for t in tokens if _es_ruido(t)}
    if coladas:
        raise ListaDeNombresInvalida(
            f"El directorio dejó pasar ruido como nombre propio: {sorted(coladas)}"
        )
    return completos, tokens


def _patron_nombres() -> re.Pattern:
    """Un solo regex compilado con nombres completos y tokens sueltos, más largos primero.

    Compilarlo una vez y reusarlo es lo que hace viable correr esto sobre
    miles de notas: la alternativa —un `re.search` por nombre y por nota— es
    cuadrática en el tamaño del directorio. Ordenar por longitud descendente
    hace que un nombre completo (p. ej. "Ana del Carmen Soto") gane la
    alternancia regex antes que cualquiera de sus tokens sueltos.
    """
    global _patron_nombres_cache
    if _patron_nombres_cache is None:
        completos, tokens = _tokens_directorio()
        candidatos = sorted(completos | tokens, key=len, reverse=True)
        alternativas = "|".join(re.escape(n) for n in candidatos) or r"(?!)"
        _patron_nombres_cache = re.compile(rf"\b(?:{alternativas})\b")
    return _patron_nombres_cache


def _patron_clientes() -> re.Pattern:
    global _patron_clientes_cache
    if _patron_clientes_cache is None:
        clientes = sorted(CLIENTES_EN_TEXTO, key=len, reverse=True)
        alternativas = "|".join(re.escape(c) for c in clientes) or r"(?!)"
        _patron_clientes_cache = re.compile(alternativas)
    return _patron_clientes_cache


def redactar(texto: str, _conteo: collections.Counter | None = None) -> str:
    """Devuelve `texto` con nombres, clientes, montos, ids y contactos redactados.

    Cada nombre distinto que aparece en la nota se numera (`[PERSONA_1]`,
    `[PERSONA_2]`, ...) para conservar si la nota habla de una persona o de
    varias, sin conservar de cuál.

    `_conteo`, si se pasa, acumula cuántas veces matcheó cada nombre exacto —
    lo usa `redactar_lote()` para auditar la corrida completa. No lo pasan
    los llamadores normales (`provider.procesar_nota()` procesa una nota a la
    vez, sin señal estadística de corrida).
    """
    t = texto
    t = _ID_BUKER.sub("[ID]", t)
    t = _EMAIL.sub("[CONTACTO]", t)
    t = _MONTO.sub("[MONTO]", t)
    t = _patron_clientes().sub("[CLIENTE]", t)

    vistos: dict[str, str] = {}

    def _reemplazo(m: re.Match) -> str:
        nombre = m.group(0)
        if _conteo is not None:
            _conteo[nombre] += 1
        if nombre not in vistos:
            vistos[nombre] = f"[PERSONA_{len(vistos) + 1}]"
        return vistos[nombre]

    return _patron_nombres().sub(_reemplazo, t)


UMBRAL_CONCENTRACION = 0.20


def redactar_lote(textos: list[str]) -> list[str]:
    """Redacta una lista de notas y audita que ningún nombre concentre >20% de la corrida.

    Es la guarda por corrida: si un solo token domina las redacciones de
    personas muy por encima de lo esperable para nombres reales —el patrón
    exacto del bug de "del"—, se detiene con un error explícito en vez de
    seguir redactando en silencio. Defensa en profundidad además de la Capa 1
    (filtro de partículas/títulos): cubre el caso de un directorio futuro con
    un tipo de ruido que la Capa 1 todavía no conoce.
    """
    conteo: collections.Counter[str] = collections.Counter()
    redactadas = [redactar(t, _conteo=conteo) for t in textos]

    total = sum(conteo.values())
    if total:
        token, n = conteo.most_common(1)[0]
        if n / total > UMBRAL_CONCENTRACION:
            raise TasaRedaccionSospechosa(
                f"'{token}' concentra {n}/{total} ({n / total:.0%}) de las "
                "redacciones de personas de la corrida — revisar el directorio."
            )
    return redactadas
