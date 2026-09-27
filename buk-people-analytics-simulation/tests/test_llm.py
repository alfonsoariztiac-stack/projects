"""
Pruebas del módulo `src/llm/`. Sin red: cubren scrubber y schema, que son
determinismo puro. `procesar_nota()` (la parte que sí llama a Gemini) se
verifica aparte, en `src/llm/evaluar.py`, contra la caché o en vivo.

Se corre con `python tests/test_llm.py` — el proyecto no trae un framework de
tests, y agregar uno para esto sería más ceremonia que la que amerita medio
día de trabajo. Cada función es una garantía y termina en un `assert`.
"""

from __future__ import annotations

import pathlib
import sys

import pandas as pd

RAIZ = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "src" / "llm"))

from schema import RespuestaInvalida, validar  # noqa: E402
from scrubber import _es_ruido, redactar  # noqa: E402

BITACORA = RAIZ / "data" / "raw" / "gs_desarrollo_bitacora.xlsx"
DIRECTORIO = RAIZ / "data" / "raw" / "bq_directorio_personas.csv"


def test_scrubber_quita_nombre_cliente_monto_id_email() -> None:
    nombres = pd.read_csv(DIRECTORIO, usecols=["nombre"])["nombre"].dropna()
    nombre_real, apellido_real = str(nombres.iloc[0]).split()[:2]

    texto = (
        f"Conversé con {nombre_real} {apellido_real} (BUK00042, "
        f"{nombre_real.lower()}@buk.example) sobre el proyecto con Andes Retail. "
        f"Plantea que su renta debería subir $1.200.000 o 15% este ciclo."
    )
    limpio = redactar(texto)

    assert nombre_real not in limpio, f"'{nombre_real}' sobrevivió al scrubber"
    assert apellido_real not in limpio, f"'{apellido_real}' sobrevivió al scrubber"
    assert "BUK00042" not in limpio
    assert "@buk.example" not in limpio
    assert "Andes Retail" not in limpio
    assert "$1.200.000" not in limpio
    assert "[PERSONA_1]" in limpio
    assert "[CLIENTE]" in limpio
    assert "[MONTO]" in limpio
    assert "[ID]" in limpio
    assert "[CONTACTO]" in limpio


def test_scrubber_numera_personas_distintas_por_nota() -> None:
    nombres = pd.read_csv(DIRECTORIO, usecols=["nombre"])["nombre"].dropna()
    n1 = str(nombres.iloc[0]).split()[0]
    n2 = str(nombres.iloc[1]).split()[0]
    assert n1 != n2

    limpio = redactar(f"{n1} lo conversó con {n2} en el 1:1. {n1} quedó conforme.")
    assert limpio.count("[PERSONA_1]") == 2
    assert limpio.count("[PERSONA_2]") == 1


def test_scrubber_no_deja_pasar_ningun_nombre_del_directorio_sobre_muestra_real() -> None:
    """La prueba que sostiene el argumento de privacidad del eje 2: sobre una
    muestra real de bitácora, ningún nombre propio conocido del directorio
    sobrevive a la redacción.

    El set de "nombres" replica el mismo filtro que usa `_tokens_directorio()`
    (partículas/títulos fuera, mayúscula inicial exigida): sin ese filtro esta
    prueba pide que el scrubber redacte "del" como si fuera una persona, que
    es exactamente el bug que se corrigió.
    """
    df = pd.read_excel(BITACORA, sheet_name="Bitácora")
    muestra = df["nota"].sample(n=min(300, len(df)), random_state=7)
    nombres = {
        p for n in pd.read_csv(DIRECTORIO, usecols=["nombre"])["nombre"].dropna()
        for p in str(n).split() if len(p) >= 3 and p[:1].isupper() and not _es_ruido(p)
    }

    fugas = []
    for nota in muestra:
        limpio = redactar(nota)
        for palabra in limpio.replace(",", " ").replace(".", " ").split():
            if palabra.strip("[]_0123456789") == palabra and palabra in nombres:
                fugas.append((nota, palabra))
    assert not fugas, f"nombres del directorio sin redactar: {fugas[:5]}"


def _resp_valida() -> dict:
    return {
        "sentimiento": "negativo",
        "temas": ["carga_trabajo", "reconocimiento"],
        "senales": ["carga_trabajo"],
        "citas_respaldo": ["trabajando fuera de horario"],
        "confianza": 0.8,
    }


def test_schema_acepta_respuesta_bien_formada() -> None:
    texto = "Relata que lleva semanas trabajando fuera de horario de forma sistemática."
    validar(_resp_valida(), texto)  # no debe lanzar


def test_schema_rechaza_tema_fuera_de_enum() -> None:
    resp = _resp_valida()
    resp["temas"] = ["carga_trabajo", "chisme_de_pasillo"]
    try:
        validar(resp, "trabajando fuera de horario")
        raise AssertionError("debió rechazar un tema fuera del enum")
    except RespuestaInvalida:
        pass


def test_schema_rechaza_cita_que_no_esta_en_el_texto() -> None:
    resp = _resp_valida()
    resp["citas_respaldo"] = ["dijo que iba a renunciar mañana"]
    try:
        validar(resp, "trabajando fuera de horario")
        raise AssertionError("debió rechazar una cita no verificable")
    except RespuestaInvalida:
        pass


def test_schema_rechaza_senal_que_no_esta_en_temas() -> None:
    resp = _resp_valida()
    resp["senales"] = ["compensacion"]  # no está en "temas"
    try:
        validar(resp, "trabajando fuera de horario")
        raise AssertionError("debió rechazar una señal fuera de 'temas'")
    except RespuestaInvalida:
        pass


def test_schema_rechaza_insuficiente_con_evidencia_adjunta() -> None:
    resp = {
        "sentimiento": "insuficiente", "temas": ["carga_trabajo"], "senales": [],
        "citas_respaldo": [], "confianza": 0.3,
    }
    try:
        validar(resp, "algo")
        raise AssertionError("insuficiente con temas debió fallar")
    except RespuestaInvalida:
        pass


if __name__ == "__main__":
    pruebas = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for prueba in pruebas:
        prueba()
        print(f"OK  {prueba.__name__}")
    print(f"\n{len(pruebas)} pruebas pasaron.")
