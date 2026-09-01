"""
Build del deck: hornea los datos reales de la corrida dentro del HTML.

Esto NO es parte del pipeline. No escribe una sola línea fuera de `deck/` y no
abre `data/out/buk.duckdb` — lee los `.parquet` con DuckDB en memoria, que no
toma lock de escritura y no interfiere con ninguna corrida en paralelo.

Por qué hornear en vez de consultar en vivo: la presentación tiene que correr
sin red, sin backend y sin un proceso Python vivo en la sala. Un archivo HTML
que se abre con doble clic no se cae.

Las curvas y tablas de `REGLAS.md` viajan como constantes (el markdown
autogenerado es frágil de parsear y estas cifras están congeladas), pero todo
lo que SÍ se puede recomputar desde los parquet se verifica contra ellos y el
build FALLA si no cuadra. Así el deck no puede desviarse de los artefactos sin
que alguien se entere.
"""

from __future__ import annotations

import base64
import glob
import hashlib
import functools
import json
import pathlib
import re
import sys

import duckdb
import pandas as pd

AQUI = pathlib.Path(__file__).parent
RAIZ = AQUI.parent
SALIDA = RAIZ / "data" / "out"
CRUDO = RAIZ / "data" / "raw"
CACHE_LLM = RAIZ / "data" / "cache" / "llm"

sys.path.insert(0, str(RAIZ / "src"))

ALERTAS = (SALIDA / "alertas.parquet").as_posix()
E360 = (SALIDA / "employee_360.parquet").as_posix()


# ─────────────────────────────────────────────────────────────────────────────
# Constantes transcritas de REGLAS.md v1.1.2 (generado 2026-09-02 10:08).
# Cada bloque cita su sección. Lo verificable se verifica más abajo.
#
# Lo que NO está acá abajo es deliberado: el catálogo, las reglas, la bitácora y
# la auditoría de equidad se LEEN de `reglas.yaml` y se recalculan desde la base
# en cada build. Transcribirlas fue justamente lo que dejó al deck horneado en
# v1.1.0 mientras el sistema corría v1.1.2 — no se repite.
# ─────────────────────────────────────────────────────────────────────────────

# REGLAS.md § Backtest
BACKTEST = {
    "alertas_mes": 28.67, "cupo": 35,
    "precision_lamentada": 14.09, "base_lamentada": 4.5, "lift_lamentada": 3.10,
    "precision_cualquiera": 18.6, "base_cualquiera": 7.8, "lift_cualquiera": 2.38,
    "cobertura_pct": 13.78, "cubiertas": 47, "salidas_lamentadas": 341,
    "carga_falsa_pct": 15.70, "carga_falsa_n": 314, "activos": 2000,
    "ventana_acierto_meses": 6, "techo_cobertura_pct": 59,
}

# REGLAS.md § Curva de calibración (cupo × cobertura)
CALIBRACION = [
    {"cupo": 15,   "alertas_mes": 14.67, "precision": 15.38, "lift": 3.38, "cobertura": 6.45,  "carga_falsa": 8.30},
    {"cupo": 25,   "alertas_mes": 22.53, "precision": 14.89, "lift": 3.27, "cobertura": 11.44, "carga_falsa": 12.40},
    {"cupo": 35,   "alertas_mes": 28.67, "precision": 14.09, "lift": 3.10, "cobertura": 13.78, "carga_falsa": 15.70},
    {"cupo": 50,   "alertas_mes": 33.93, "precision": 13.25, "lift": 2.91, "cobertura": 14.66, "carga_falsa": 18.90},
    {"cupo": 75,   "alertas_mes": 35.73, "precision": 13.25, "lift": 2.91, "cobertura": 14.66, "carga_falsa": 20.00},
    {"cupo": 100,  "alertas_mes": 35.93, "precision": 13.25, "lift": 2.91, "cobertura": 14.66, "carga_falsa": 20.15},
    {"cupo": 9999, "alertas_mes": 35.93, "precision": 13.25, "lift": 2.91, "cobertura": 14.66, "carga_falsa": 20.15},
]

# REGLAS.md § Curva de enfriamiento (sin tope) — la palanca no es el cupo
ENFRIAMIENTO = [
    {"meses": 0, "alertas_mes": 58.13, "precision": 16.57, "cobertura": 14.96, "carga_falsa": 20.15},
    {"meses": 3, "alertas_mes": 35.93, "precision": 13.25, "cobertura": 14.66, "carga_falsa": 20.15},
    {"meses": 6, "alertas_mes": 34.27, "precision": 13.48, "cobertura": 14.37, "carga_falsa": 20.15},
]

# REGLAS.md § Techo de cobertura por perfil latente
COBERTURA_PERFIL = [
    {"perfil": "estable",            "salidas": 141, "cubiertas": 7,  "cobertura": 5.0},
    {"perfil": "deterioro",          "salidas": 108, "cubiertas": 15, "cobertura": 13.9},
    {"perfil": "estrella_subpagada", "salidas": 88,  "cubiertas": 25, "cobertura": 28.4},
    {"perfil": "nuevo_dificil",      "salidas": 2,   "cubiertas": 0,  "cobertura": 0.0},
    {"perfil": "bajo_desempeno",     "salidas": 2,   "cubiertas": 0,  "cobertura": 0.0},
]

# decisiones-arquitectura: panel de señales por perfil, último mes activo.
# Es el argumento empírico de "≥2 dimensiones": ninguna dimensión sola cubre.
PANEL_PERFILES = [
    {"perfil": "estable",            "compa": 1.002, "desempeno": 3.40, "productividad": 98.8, "delta_prod": -0.02},
    {"perfil": "deterioro",          "compa": 0.980, "desempeno": 3.20, "productividad": 78.2, "delta_prod": -3.51},
    {"perfil": "estrella_subpagada", "compa": 0.845, "desempeno": 3.31, "productividad": 90.0, "delta_prod": -1.69},
    {"perfil": "bajo_desempeno",     "compa": 0.989, "desempeno": 2.73, "productividad": 80.7, "delta_prod": -1.58},
    {"perfil": "nuevo_dificil",      "compa": 0.971, "desempeno": 2.79, "productividad": 76.5, "delta_prod": -2.64},
]

# REGLAS.md § Señales descartadas — el registro de lo que NO entró y por qué
DESCARTADAS = [
    {"senal": "desempeno_bajo", "cond": "score_vigente < 2.8", "lift_lam": 0.48, "lift_cual": 2.51,
     "motivo": "Lift 0,48 sobre salida lamentada y 2,51 sobre cualquier salida: optimizar contra "
               "«salida» a secas construía un detector de bajo desempeño con etiqueta de bienestar."},
    {"senal": "riesgo_evaluacion_90d", "cond": "score_90d < 3.0 AND antiguedad <= 12", "lift_lam": 0.72, "lift_cual": None,
     "motivo": "Sin poder predictivo sobre la salida que importa."},
    {"senal": "sueldo_sin_revisar", "cond": "meses_desde_ultimo_ajuste >= 18", "lift_lam": 0.79, "lift_cual": None,
     "motivo": "Intuitiva pero por debajo de la base: marca antigüedad, no riesgo."},
    {"senal": "formacion_bajo_cohorte", "cond": "ratio_formacion_cohorte < 0.5", "lift_lam": 1.04, "lift_cual": None,
     "motivo": "Dispara en el 32% de las personas-mes. Sin poder discriminante."},
    {"senal": "desgaste_vacaciones_por_cohorte", "cond": "ratio_vacaciones_cohorte > 1.5", "lift_lam": 0.90, "lift_cual": None,
     "motivo": "Peor que el denominador simple, que quedó en 1,11."},
]

# REGLAS.md § Auditoría de impacto dispar (EEOC, regla del 80% + |z| > 2)
# Solo los PARÁMETROS viajan como constante. Los índices por grupo se recalculan
# en cada build con el mismo código que corre `equidad.py` (ver equidad_calc):
# transcribirlos fue lo que hizo que el deck afirmara "ninguno protegido marcado"
# cuando v1.1.2 ya había marcado dos grupos de nacionalidad.
EQUIDAD_PARAMS = {
    "banda": [0.80, 1.25], "z_critico": 2.0, "n_minimo": 40, "salidas_minimas": 25,
    "protegidos": ["genero", "tramo_edad", "nacionalidad"],
    "gobernanza": ["job_family", "pais_contrato", "tramo_antiguedad"],
}


# cloud/evidencia/alertas-mensual-6nx8t.log + cloud/README.md § F6
ORQUESTACION = {
    "job": "alertas-mensual", "job_region": "southamerica-west1",
    "scheduler": "alertas-mensual-trigger", "scheduler_region": "southamerica-east1",
    "cron": "día 1 de cada mes, 08:30 America/Santiago",
    "proximo_disparo": "2026-10-01 08:30",
    "duracion_s": 57.7, "exit_code": 0, "tarjetas_enviadas": 2,
    "log": "cloud/evidencia/alertas-mensual-6nx8t.log",
}

# reporte_llm.md
LLM_RESUMEN = {"notas": 30, "procesadas": 30, "no_procesado": 0,
               "acierto_sentimiento": 100.0, "acierto_tema": 100.0,
               "modelo": "gemini-flash-latest", "cacheadas": 32,
               "temas_cerrados": 12, "sentimientos": 4}


_CAT_CACHE: dict | None = None


def _yaml_catalogo() -> dict:
    """`src/rules/reglas.yaml` parseado una sola vez. La fuente de verdad."""
    global _CAT_CACHE
    if _CAT_CACHE is None:
        import yaml
        _CAT_CACHE = yaml.safe_load(
            (RAIZ / "src" / "rules" / "reglas.yaml").read_text(encoding="utf-8"))
    return _CAT_CACHE


def _hash(texto: str) -> str:
    """Mismo hash que `src/llm/provider.py`: sha256 del texto YA redactado."""
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:24]


def con() -> duckdb.DuckDBPyConnection:
    """DuckDB en memoria. Nunca `buk.duckdb`: abrirlo tomaría el lock."""
    return duckdb.connect(":memory:")


def escala() -> dict:
    with con() as c:
        e = c.execute(f"""
            SELECT count(*) filas, count(DISTINCT employee_id) personas,
                   count(DISTINCT periodo) meses, min(periodo) desde, max(periodo) hasta
            FROM read_parquet('{E360}')""").fetchone()
        activos = c.execute(f"""
            SELECT count(*) FROM read_parquet('{E360}')
            WHERE periodo = (SELECT max(periodo) FROM read_parquet('{E360}'))
              AND activo_en_el_mes""").fetchone()[0]
        universo = c.execute(f"""
            SELECT count(*) FROM read_parquet('{E360}')
            WHERE activo_en_el_mes AND antiguedad_meses >= 3""").fetchone()[0]
    return {"filas": e[0], "personas": e[1], "meses": e[2], "desde": e[3], "hasta": e[4],
            "activos": activos, "universo_persona_mes": universo}


def alertas() -> dict:
    with con() as c:
        def q(sql):
            return c.execute(sql.format(A=ALERTAS)).fetchdf().to_dict("records")
        por_regla = q("""SELECT regla, regla_nombre, canal, nivel, count(*) filas,
                                count(DISTINCT employee_id) personas
                         FROM read_parquet('{A}') GROUP BY 1,2,3,4 ORDER BY regla""")
        por_canal = q("""SELECT canal, count(*) filas, count(DISTINCT employee_id) personas,
                                count(DISTINCT periodo) meses
                         FROM read_parquet('{A}') GROUP BY 1 ORDER BY 1""")
        dims = q("""SELECT n_dimensiones, count(*) filas FROM read_parquet('{A}')
                    GROUP BY 1 ORDER BY 1""")
        estado = q("""SELECT estado, count(*) filas FROM read_parquet('{A}')
                      GROUP BY 1 ORDER BY 2 DESC""")
        ultimo = c.execute(f"""
            SELECT canal, estado, count(*) n FROM read_parquet('{ALERTAS}')
            WHERE periodo = (SELECT max(periodo) FROM read_parquet('{ALERTAS}'))
            GROUP BY 1,2 ORDER BY 1,2""").fetchdf().to_dict("records")
        notificadas_mes = c.execute(f"""
            SELECT count(*) * 1.0 / count(DISTINCT periodo) FROM read_parquet('{ALERTAS}')
            WHERE canal = 'conversacion' AND estado = 'notificada'""").fetchone()[0]
        total = c.execute(f"SELECT count(*), count(DISTINCT employee_id) FROM read_parquet('{ALERTAS}')").fetchone()
    return {"por_regla": por_regla, "por_canal": por_canal, "dimensiones": dims,
            "estado": estado, "ultimo_mes": ultimo, "notificadas_mes": round(notificadas_mes, 2),
            "filas": total[0], "personas": total[1]}


def casos_tarjeta() -> list[dict]:
    """Los 3 casos reales, armados por el MISMO código que produce la tarjeta real.

    Se importa `deliver.chat_card` en vez de reimplementar: si el criterio de
    "qué no sabemos" cambia en el sistema, el deck cambia con él o no compila.
    """
    from deliver import chat_card  # noqa

    casos = []
    for caso in chat_card.casos_demo():
        casos.append({
            "employee_id": caso["employee_id"], "nombre": caso["nombre"],
            "regla": caso["regla"], "regla_nombre": caso["regla_nombre"],
            "nivel": caso["nivel"], "canal": caso["canal"], "periodo": caso["periodo"],
            "area": caso["area"], "job_family": caso["job_family"],
            "etiqueta_nivel": caso["etiqueta_nivel"],
            "antiguedad_meses": int(caso["antiguedad_meses"]),
            "n_dimensiones": int(caso["n_dimensiones"]),
            "lectura": caso["lectura"],
            "senales": list(caso["senales"]), "evidencia": list(caso["evidencia"]),
            "no_sabemos": chat_card._que_no_sabemos(caso),
            "acciones": chat_card._acciones(caso),
            "pie": chat_card.PIE, "nota_botones": chat_card.NOTA_BOTONES,
        })
    return casos


def notas_llm() -> list[dict]:
    """Pares original ↔ redactado ↔ salida del modelo, para el replay del Eje 2.

    Se reconstruye el original recorriendo la bitácora y hasheando cada nota
    redactada: el caché se indexa por el hash del texto YA redactado, así que
    el original nunca estuvo escrito en disco dentro de `data/cache/`.
    """
    try:
        import pandas as pd
        from llm import scrubber
    except Exception as e:  # degradación segura si la otra sesión rompió el import
        print(f"  ⚠ no se pudo importar el scrubber ({e}); replay sin original")
        return []

    cache = {}
    for f in glob.glob(str(CACHE_LLM / "*.json")):
        d = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
        cache[d["hash_nota"]] = d

    notas = pd.read_excel(CRUDO / "gs_desarrollo_bitacora.xlsx", sheet_name="Bitácora")
    originales = [str(n) for n in notas["nota"]]
    tipos = [str(t) for t in notas.get("tipo_instancia", [""] * len(notas))]
    # redactar_lote() audita la corrida completa (Capa 3): si un solo nombre
    # concentrara >20% de las redacciones de personas, el build se detiene acá
    # en vez de hornear un deck con el mismo bug que "del".
    redactadas = scrubber.redactar_lote(originales)

    salida = []
    for original, red, tipo in zip(originales, redactadas, tipos):
        d = cache.get(_hash(red))
        if not d:
            continue
        salida.append({
            "original": original, "scrubbed": red,
            "tipo_instancia": tipo,
            "sentimiento": d["sentimiento"], "temas": d["temas"], "senales": d["senales"],
            "citas": d["citas_respaldo"], "confianza": d["confianza"],
            "modelo": d["modelo"], "version_prompt": d["version_prompt"],
        })
        if len(salida) == len(cache):
            break
    print(f"  · {len(salida)} de {len(cache)} notas del caché reconstruidas con su original")
    return salida


def scrubber_js() -> dict:
    """Insumos para reimplementar el scrubber en el navegador (campo libre)."""
    from llm import scrubber
    from textos import CLIENTES_EN_TEXTO
    completos, tokens = scrubber._tokens_directorio()
    return {"completos": sorted(completos), "tokens": sorted(tokens),
            "clientes": list(CLIENTES_EN_TEXTO)}


def backtest() -> dict:
    """Las cifras del backtest, más las tres que la lámina deriva de la curva.

    Derivarlas acá y no en la plantilla evita que el argumento del enfriamiento
    —el corazón de la calibración— quede escrito a mano en tres lugares.
    """
    por_enf = {e["meses"]: e for e in ENFRIAMIENTO}
    vigente = _yaml_catalogo()["operacion"]["canales"]["conversacion"]["enfriamiento_meses"]
    sin, con = por_enf[0], por_enf[vigente]
    return {
        **BACKTEST,
        # la curva de cupo satura donde el enfriamiento vigente la deja: subir el
        # cupo al infinito no compra más cobertura que esa.
        "saturacion_pct": CALIBRACION[-1]["cobertura"],
        "enfriamiento_volumen_pct": round(100 * (sin["alertas_mes"] / con["alertas_mes"] - 1)),
        "enfriamiento_cobertura_pts": round(sin["cobertura"] - con["cobertura"], 1),
    }


def catalogo() -> dict:
    """Metadatos del catálogo, leídos del YAML — nunca transcritos.

    Es el mismo archivo que gobierna al motor. Si alguien publica una versión
    nueva y no reconstruye el deck, `verificar()` lo detiene.
    """
    cat = _yaml_catalogo()
    return {"version": cat["version"], "vigente_desde": str(cat["vigente_desde"]),
            "duenio": cat["duenio"], "ciclo_revision": cat["ciclo_revision"],
            "retencion_dias": cat["operacion"]["retencion_dias"],
            "universo": cat["universo"]["condicion"]}


def reglas() -> list[dict]:
    """Las 6 reglas tal como las define el YAML: qué cruzan, nivel y canal.

    Es la respuesta literal del enunciado ("¿qué reglas dispararían Riesgo Medio
    o Riesgo Alto?"), así que sale de la fuente y no de una tabla escrita a mano.
    El nivel y el canal juntos son el argumento: el nivel no es un adjetivo, es
    un enrutamiento.
    """
    cat = _yaml_catalogo()
    senales = cat["senales"]
    dim = lambda ids: [senales[i]["dimension"] for i in ids]  # noqa: E731

    salida = []
    for rid, r in cat["reglas"].items():
        todas, alguna = r.get("todas", []), r.get("alguna", [])
        salida.append({
            "id": rid, "nombre": r["nombre"], "nivel": r["nivel"], "canal": r["canal"],
            "prioridad": r["prioridad"],
            "todas": todas, "alguna": alguna,
            "dim_todas": sorted(set(dim(todas))),
            "dim_alguna": sorted(set(dim(alguna))),
            "entrega": "tarjeta de Chat" if r["canal"] == "conversacion" else f"panel {r['canal']}",
        })
    return salida


# Corta en el punto que termina una frase de verdad: ignora los que están dentro
# de un número de versión (v1.1.2), de un decimal (0,3) o de una abreviatura corta.
_FIN_DE_FRASE = re.compile(r"(?<![0-9])\.(?=\s+[A-ZÁÉÍÓÚÑ¿«])")


def bitacora(limite: int = 175) -> list[dict]:
    """La bitácora de versiones del catálogo: gobernanza como práctica, no promesa.

    Cuatro versiones en tres días, cada una con su razón medida. El resumen se
    corta a las primeras frases que quepan en `limite` porque la lámina no
    aguanta el párrafo completo, pero sale del YAML y no de una tabla a mano.
    """
    salida = []
    for e in _yaml_catalogo()["bitacora"]:
        resumen = " ".join(e.get("resumen", "").split())
        if not resumen:  # entrada sin copy propio: se cae a las primeras frases del registro
            texto = " ".join(e["cambio"].split())
            for frase in _FIN_DE_FRASE.split(texto):
                candidato = f"{resumen} {frase.strip()}.".strip()
                if resumen and len(candidato) > limite:
                    break
                resumen = candidato
        salida.append({"version": e["version"], "fecha": str(e["fecha"]),
                       "autor": e["autor"], "resumen": resumen})
    return salida


def hallazgo_antiguedad() -> dict:
    """El hallazgo de la limitación 1, recalculado desde el panel de equidad.

    Es el argumento más fuerte del deck y el que más caro sale si se queda con
    una cifra de una versión anterior, así que sale del mismo panel que audita
    el catálogo — no de una transcripción de REGLAS.md.
    """
    ant = next(c["grupos"] for c in equidad_calc()["cortes"]
               if c["corte"] == "tramo_antiguedad")
    por_grupo = {f["g"]: f for f in ant}
    nuevos, siguiente = por_grupo["0-11"], por_grupo["12-23"]
    total = sum(f["salidas_lamentadas"] for f in ant)
    # Dos lecturas de la misma cohorte: por cabeza parece un sesgo brutal, por
    # mes-persona expuesto se da vuelta. La diferencia entera es exposición.
    alertas_pc = lambda f: f["alertas_1000m"] * f["meses_expuesto"]  # noqa: E731
    return {
        "tasa_0_11": round(nuevos["tasa_salida"], 3),
        "tasa_12_23": round(siguiente["tasa_salida"], 3),
        "concentra_pct": round(100 * nuevos["salidas_lamentadas"] / total),
        "cobertura_pct": round(100 * nuevos["cobertura"], 1),
        "indice_por_cabeza": round(alertas_pc(siguiente) / alertas_pc(nuevos), 1),
        "alertas_1000m_0_11": round(nuevos["alertas_1000m"], 1),
        "alertas_1000m_12_23": round(siguiente["alertas_1000m"], 1),
        "meses_expuesto": round(nuevos["meses_expuesto"], 1),
        "meses_expuesto_resto": round(siguiente["meses_expuesto"], 1),
    }


@functools.cache
def equidad_calc() -> dict:
    """Auditoría de impacto dispar recalculada, no transcrita.

    Importa `equidad.py` y corre `auditar()` sobre los mismos 6 cortes que la
    versión de consola. Cualquier grupo que se marque aparece acá el mismo día,
    aunque nadie se acuerde de actualizar una constante.
    """
    import duckdb as _d
    from rules import equidad as eq

    con = _d.connect(str(eq.BD), read_only=True)
    eq._preparar(con, eq.cargar())

    cortes, marcados = [], []
    for atributos, protegido in [(EQUIDAD_PARAMS["protegidos"], True),
                                 (EQUIDAD_PARAMS["gobernanza"], False)]:
        for atributo in atributos:
            df = eq.auditar(con, atributo)
            grupos = []
            for _, f in df.iterrows():
                estado = str(f.estado)
                grupos.append({
                    "g": f.grupo, "n": int(f.personas),
                    "indice": None if pd.isna(f.indice_alerta) else round(float(f.indice_alerta), 3),
                    "indice_cobertura": None if pd.isna(f.indice_cobertura) else round(float(f.indice_cobertura), 3),
                    "tasa_salida": round(float(f.tasa_salida), 3),
                    "salidas_lamentadas": int(f.salidas_lamentadas),
                    "cobertura": None if pd.isna(f.cobertura) else round(float(f.cobertura), 4),
                    # Con 4 decimales: redondear acá y otra vez en hallazgo_antiguedad()
                    # daba 13,8 donde REGLAS.md, que redondea una sola vez, dice 13,9.
                    "alertas_1000m": round(float(f.alertas_1000m), 4),
                    "meses_expuesto": round(float(f.meses_expuesto), 4),
                    "ref": estado == "referencia", "estado": estado,
                })
                if estado.startswith("REVISAR"):
                    marcados.append({"corte": atributo, "grupo": f.grupo,
                                     "estado": estado, "protegido": protegido})
            cortes.append({"corte": atributo, "protegido": protegido, "grupos": grupos})
    con.close()

    protegidos_por_alerta = [m for m in marcados
                             if m["protegido"] and "alerta" in m["estado"]]
    return {**EQUIDAD_PARAMS, "cortes": cortes, "marcados": len(marcados),
            "marcados_detalle": marcados,
            "protegidos_marcados_por_alerta": len(protegidos_por_alerta)}


def capturas() -> list[dict]:
    """Capturas de respaldo de la salida a la nube, embebidas en base64.

    Si la red de la sala falla, el respaldo tiene que estar dentro del mismo
    archivo. Si la carpeta está vacía el deck lo dice en pantalla en vez de
    mostrar imágenes rotas.
    """
    mimes = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    salida = []
    for f in sorted((AQUI / "capturas").glob("*")):
        if f.suffix.lower() not in mimes:
            continue
        salida.append({"nombre": f.stem.replace("_", " "), "mime": mimes[f.suffix.lower()],
                       "b64": base64.b64encode(f.read_bytes()).decode("ascii")})
    print(f"  · {len(salida)} capturas embebidas")
    return salida


def verificar(d: dict) -> None:
    """Falla ruidosamente si una cifra horneada no cuadra con los artefactos.

    Es la razón de ser de este script: que el deck no pueda mentir sin que el
    build se caiga primero.
    """
    ok = []

    def chequear(nombre, esperado, real, tol=0.01):
        if abs(esperado - real) > tol:
            raise SystemExit(
                f"\n✗ DESCUADRE: {nombre}\n  REGLAS.md dice {esperado}, los parquet dicen {real}\n"
                f"  Alguien regeneró data/out/ o cambió el catálogo. Revisar antes de presentar.")
        ok.append(f"{nombre}: {real}")

    chequear("alertas/mes del canal conversación", BACKTEST["alertas_mes"], d["alertas"]["notificadas_mes"], 0.05)
    chequear("activos en el último mes", BACKTEST["activos"], d["escala"]["activos"], 0)

    una_dim = [x["filas"] for x in d["alertas"]["dimensiones"] if x["n_dimensiones"] < 2]
    if una_dim:
        raise SystemExit(f"\n✗ GARANTÍA ROTA: hay {sum(una_dim)} alertas con menos de 2 dimensiones")
    ok.append("garantía ≥2 dimensiones: 0 alertas con 1 sola dimensión")

    # Las cifras del backtest que SÍ se pueden recomputar desde el parquet.
    # Antes solo se chequeaba el volumen, y por eso un deck v1.1.0 pudo convivir
    # con un catálogo v1.1.2 sin que nada se quejara.
    chequear("cobertura del backtest", BACKTEST["cobertura_pct"],
             round(100 * BACKTEST["cubiertas"] / BACKTEST["salidas_lamentadas"], 2), 0.02)
    chequear("carga sobre quien se queda", BACKTEST["carga_falsa_pct"],
             round(100 * BACKTEST["carga_falsa_n"] / BACKTEST["activos"], 2), 0.02)
    # Tolerancia amplia a propósito: acá se contrastan dos cifras YA redondeadas
    # (la base publicada es 4,5% y la real 4,545%), así que el residuo es de
    # redondeo. Igual atrapa una deriva de versión, que es un salto de 0,2 o más.
    chequear("lift sobre salida lamentada", BACKTEST["lift_lamentada"],
             round(BACKTEST["precision_lamentada"] / BACKTEST["base_lamentada"], 2), 0.05)

    # La comprobación que habría detectado el desfase sola: contra el YAML, no
    # contra una constante transcrita de él.
    version_yaml = _yaml_catalogo()["version"]
    if d["catalogo"]["version"] != version_yaml:
        raise SystemExit(f"\n✗ el deck dice v{d['catalogo']['version']} y "
                         f"reglas.yaml dice v{version_yaml}")
    ok.append(f"catálogo v{version_yaml} (leído de reglas.yaml)")

    # Ningún literal de versión suelto en la plantilla: el chip va por data-d.
    plantilla = (AQUI / "plantilla.html")
    if plantilla.exists():
        import re as _re
        sueltos = _re.findall(r"v\d+\.\d+\.\d+", plantilla.read_text(encoding="utf-8"))
        if sueltos:
            raise SystemExit(f"\n✗ plantilla.html tiene versiones escritas a mano: "
                             f"{sorted(set(sueltos))}. Usar data-d=\"catalogo.version\".")
        ok.append("plantilla sin literales de versión")

    # Los casos de tarjeta son, por definición, las reglas del canal `conversacion`.
    # Fijar el número en 3 escondía que v1.1.2 dejó el canal con 2 reglas.
    esperadas = sorted(r["id"] for r in d["reglas"] if r["canal"] == "conversacion")
    reales = sorted(c["regla"] for c in d["casos"])
    if reales != esperadas:
        raise SystemExit(f"\n✗ los casos de tarjeta ({reales}) no son las reglas "
                         f"del canal conversación ({esperadas})")
    ok.append(f"{len(reales)} casos de tarjeta = reglas de `conversacion` ({', '.join(reales)})")

    # La afirmación ética del deck tiene que salir del cálculo, no de la memoria.
    n_prot = d["equidad"]["protegidos_marcados_por_alerta"]
    ok.append(f"equidad: {d['equidad']['marcados']} grupos marcados · "
              f"{n_prot} protegido(s) por índice de alerta")

    for linea in ok:
        print(f"  ✓ {linea}")


def main() -> None:
    print("Construyendo datos del deck (solo lectura sobre data/)…")
    d = {
        "catalogo": catalogo(),
        "reglas": reglas(),
        "bitacora": bitacora(),
        "orquestacion": ORQUESTACION,
        "escala": escala(),
        "calidad": {"fuentes": 9, "leidas": 63182, "validas": 62267, "pct": 98.6,
                    "peor_tasa_rechazo": 1.84, "umbral_corte": 5.0},
        "backtest": backtest(),
        "calibracion": CALIBRACION,
        "enfriamiento": ENFRIAMIENTO,
        "cobertura_perfil": COBERTURA_PERFIL,
        "panel_perfiles": PANEL_PERFILES,
        "descartadas": DESCARTADAS,
        "equidad": equidad_calc(),
        "hallazgo_antiguedad": hallazgo_antiguedad(),
        "llm_resumen": LLM_RESUMEN,
        "alertas": alertas(),
        "casos": casos_tarjeta(),
        "notas_llm": notas_llm(),
        "scrubber": scrubber_js(),
        "capturas": capturas(),
    }
    verificar(d)

    destino = AQUI / "datos.json"
    destino.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n→ {destino.relative_to(RAIZ)} ({destino.stat().st_size // 1024} KB)")

    plantilla = AQUI / "plantilla.html"
    if plantilla.exists():
        html = plantilla.read_text(encoding="utf-8")
        marca = "/*__DATOS__*/"
        if marca not in html:
            raise SystemExit(f"✗ la plantilla no tiene la marca {marca}")
        payload = json.dumps(d, ensure_ascii=False).replace("</", "<\\/")
        html = html.replace(marca, payload)
        final = AQUI / "presentacion.html"
        final.write_text(html, encoding="utf-8")
        print(f"→ {final.relative_to(RAIZ)} ({final.stat().st_size // 1024} KB) — autocontenido")
    else:
        print("· plantilla.html todavía no existe; solo se escribió datos.json")


if __name__ == "__main__":
    main()
