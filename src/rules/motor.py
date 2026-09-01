"""
Motor de reglas: convierte `reglas.yaml` en SQL y el SQL en alertas.

Tres cosas que este archivo hace y que valen más que el código:

1. **No contiene ninguna regla.** Toda la lógica de negocio vive en el YAML.
   Este módulo la lee, la valida y la compila. Si alguien quiere saber por qué
   se alertó a una persona, la respuesta está en un archivo que puede leer sin
   saber Python.

2. **Verifica las garantías antes de correr, no después.** Que ninguna regla
   toque un atributo protegido y que toda alerta se apoye en al menos dos
   dimensiones no son promesas del diseño: son `assert` que detienen el
   pipeline. Una garantía que no falla ruidosamente no es una garantía.

3. **El SQL que emite es el que correría en BigQuery.** Mismo subconjunto que
   `src/sql/`: sin DATE_DIFF, sin FILTER, sin ANY_VALUE, toda la aritmética de
   meses sobre el entero `idx_mes`. Se guarda en `data/out/alertas.sql` para
   poder pegarlo tal cual en la consola del warehouse.
"""

from __future__ import annotations

import pathlib
import re
import sys

import duckdb
import pandas as pd
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from warehouse import BD, RAIZ, SALIDA  # noqa: E402

CATALOGO = pathlib.Path(__file__).parent / "reglas.yaml"

# Palabras del dialecto SQL, para poder distinguir una columna de un operador
# al leer las expresiones del catálogo.
PALABRAS_SQL = {"and", "or", "not", "case", "when", "then", "else", "end",
                "is", "null", "true", "false", "cast", "as"}

# Columnas que la alerta arrastra para poder explicarse sin volver a la base.
CONTEXTO = [
    "area", "job_family", "job_level", "etiqueta_nivel", "pais_contrato",
    "manager_id", "antiguedad_meses", "tramo_antiguedad", "moneda",
    "compa_ratio", "sueldo_base", "banda_min", "score_vigente",
    "categoria_vigente", "delta_desempeno", "prod_prom_3m", "prod_delta_3m",
    "csat_prom_3m", "csat_delta_3m", "dias_sin_vacaciones", "meses_sin_nota",
]


# ---------------------------------------------------------------------------
# Carga y validación
# ---------------------------------------------------------------------------

class CatalogoInvalido(Exception):
    """El catálogo rompe una garantía del diseño. La corrida no continúa."""


def cargar(ruta: pathlib.Path = CATALOGO) -> dict:
    cat = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    validar(cat)
    return cat


def expresion(cat: dict, sid: str) -> str:
    """Resuelve la expresión SQL de una señal, sustituyendo su umbral."""
    s = cat["senales"][sid]
    return s["expr"].format(umbral=s.get("umbral"))


def columnas_leidas(cat: dict) -> list[str]:
    """Columnas de employee_360 que el motor tiene permitido leer.

    Se deduce del catálogo en vez de mantenerse a mano: lo que ninguna señal
    menciona, no se selecciona. `employee_360` contiene `fecha_salida` y
    `sale_en_3_meses` —etiquetas de resultado— y la única forma sólida de
    garantizar que no se cuelen a una alerta es no proyectarlas nunca.
    """
    usadas: set[str] = set()
    for sid in cat["senales"]:
        for token in re.findall(r"[a-z_][a-z0-9_]*", expresion(cat, sid)):
            if token not in PALABRAS_SQL:
                usadas.add(token)
    return list(dict.fromkeys(["employee_id", "periodo", "idx_mes", *CONTEXTO, *sorted(usadas)]))


def validar(cat: dict) -> None:
    """Las cuatro garantías que el diseño promete, comprobadas antes de correr.

    Se validan aquí y no en un test aparte a propósito: un catálogo inválido no
    debe poder producir alertas ni siquiera si alguien se salta la suite.
    """
    senales, reglas = cat["senales"], cat["reglas"]

    # 1 · Ninguna expresión menciona un atributo protegido ni una etiqueta de
    #     resultado. Búsqueda por palabra completa: `edad` no debe hacer match
    #     dentro de `antiguedad_meses`.
    for atributo in cat["atributos_prohibidos"]:
        patron = re.compile(rf"\b{re.escape(atributo)}\b")
        for sid, s in senales.items():
            if patron.search(s["expr"]):
                raise CatalogoInvalido(
                    f"La señal '{sid}' referencia el atributo prohibido '{atributo}'. "
                    "Los atributos protegidos se auditan (equidad.py), no se condicionan."
                )
        if patron.search(cat["universo"]["condicion"]):
            raise CatalogoInvalido(
                f"El universo referencia el atributo prohibido '{atributo}'."
            )

    for rid, r in reglas.items():
        refs = list(r.get("todas", [])) + list(r.get("alguna", []))

        # 2 · Toda señal referenciada existe.
        for sid in refs:
            if sid not in senales:
                raise CatalogoInvalido(f"La regla '{rid}' referencia la señal inexistente '{sid}'.")
        if not refs:
            raise CatalogoInvalido(f"La regla '{rid}' no referencia ninguna señal.")

        # 3 · Toda combinación que satisface la regla cubre >= 2 dimensiones.
        #     Se comprueba rama por rama: basta con que UNA opción de `alguna`
        #     deje la regla en una sola dimensión para que el catálogo sea
        #     inválido, aunque las demás opciones cumplan.
        dims_fijas = {senales[s]["dimension"] for s in r.get("todas", [])}
        ramas = [dims_fijas | {senales[s]["dimension"]} for s in r.get("alguna", [])] or [dims_fijas]
        for dims in ramas:
            if len(dims) < 2:
                raise CatalogoInvalido(
                    f"La regla '{rid}' puede cumplirse con señales de una sola dimensión "
                    f"({', '.join(sorted(dims))}). Toda alerta exige al menos dos."
                )

        # 4 · Toda combinación incluye al menos una señal de riesgo. Nadie se
        #     alerta solo por su contexto (ser sobresaliente no es un problema).
        tipos_fijos = {senales[s]["tipo"] for s in r.get("todas", [])}
        ramas_tipo = [tipos_fijos | {senales[s]["tipo"]} for s in r.get("alguna", [])] or [tipos_fijos]
        for tipos in ramas_tipo:
            if "riesgo" not in tipos:
                raise CatalogoInvalido(
                    f"La regla '{rid}' puede cumplirse solo con señales de contexto."
                )

    # 5 · Todo canal declarado por una regla tiene una capacidad asignada.
    for rid, r in reglas.items():
        if r["canal"] not in cat["operacion"]["canales"]:
            raise CatalogoInvalido(
                f"La regla '{rid}' enruta al canal '{r['canal']}', que no tiene cupo declarado."
            )

    # 6 · Las prioridades ordenan sin empates: la cola de capacidad tiene que
    #     ser determinista o el mismo mes daría alertas distintas en cada corrida.
    prioridades = [r["prioridad"] for r in reglas.values()]
    if len(set(prioridades)) != len(prioridades):
        raise CatalogoInvalido("Hay reglas con la misma prioridad; la cola no sería determinista.")


# ---------------------------------------------------------------------------
# Compilación a SQL
# ---------------------------------------------------------------------------

def condicion_regla(cat: dict, rid: str) -> str:
    """TODAS las de `todas` Y AL MENOS UNA de `alguna`, sobre las columnas s_*."""
    r = cat["reglas"][rid]
    partes = [f"s_{s}" for s in r.get("todas", [])]
    if r.get("alguna"):
        partes.append("(" + " OR ".join(f"s_{s}" for s in r["alguna"]) + ")")
    return " AND ".join(partes)


def compilar(cat: dict) -> str:
    """Genera el SQL completo. Es el artefacto que se muestra en la presentación."""
    op = cat["operacion"]
    senales = cat["senales"]
    orden = sorted(cat["reglas"], key=lambda r: cat["reglas"][r]["prioridad"])

    cols_senal = ",\n    ".join(
        f"({expresion(cat, sid)}) AS s_{sid}" for sid in senales
    )
    # Una alerta = una regla: la de mayor precisión medida entre las que se
    # cumplen. Mostrar cinco motivos a la vez no ayuda a nadie a actuar.
    caso_regla = "\n      ".join(
        f"WHEN {condicion_regla(cat, rid)} THEN '{rid}'" for rid in orden
    )
    caso_prio = "\n      ".join(
        f"WHEN {condicion_regla(cat, rid)} THEN {cat['reglas'][rid]['prioridad']}" for rid in orden
    )
    caso_canal = "\n      ".join(
        f"WHEN {condicion_regla(cat, rid)} THEN '{cat['reglas'][rid]['canal']}'" for rid in orden
    )
    # Cada canal se agota contra su propia capacidad. Una revisión de banda no
    # consume el tiempo de conversación de un Happiness Manager.
    # Un canal en modo panel no tiene cupo: no compite por atención por caso.
    caso_cupo = "\n         ".join(
        f"WHEN canal = '{canal}' AND posicion_en_cola <= {c['cupo_mensual']} THEN 'notificada'"
        if c["modo"] == "alerta" else f"WHEN canal = '{canal}' THEN 'en_panel'"
        for canal, c in op["canales"].items()
    )
    # El enfriamiento es propiedad del canal, no del sistema: un evento se deja
    # de notificar, un estado no tiene por qué enfriarse.
    caso_enfriamiento = "\n           ".join(
        f"WHEN '{canal}' THEN {c['enfriamiento_meses']}" for canal, c in op["canales"].items()
    )
    # Se recuenta la dimensión en tiempo de ejecución: la validación estática ya
    # lo garantiza, pero un dato raro (todo nulo) podría producir otra cosa y
    # queremos que la fila lo diga, no que lo suponga.
    dims = sorted({s["dimension"] for s in senales.values()})
    conteo_dim = "\n    + ".join(
        "CASE WHEN " + " OR ".join(f"s_{sid}" for sid, s in senales.items() if s["dimension"] == d)
        + " THEN 1 ELSE 0 END"
        for d in dims
    )
    cols = columnas_leidas(cat)
    proyeccion = ",\n         ".join(cols)

    return f"""\
-- Generado por src/rules/motor.py desde reglas.yaml v{cat['version']}. No editar.
-- Dialecto: subconjunto común DuckDB / BigQuery.
--
-- La proyección del universo es una lista blanca derivada del catálogo: las
-- columnas que no menciona ninguna señal no se leen. Por eso `fecha_salida` y
-- `sale_en_3_meses` no aparecen aquí ni pueden aparecer en una alerta.
WITH universo AS (
  SELECT {proyeccion}
  FROM {cat['universo']['tabla']}
  WHERE {cat['universo']['condicion']}
),
senales AS (
  SELECT
    universo.*,
    {cols_senal}
  FROM universo
),
evaluadas AS (
  SELECT
    senales.*,
    CASE
      {caso_regla}
    END AS regla,
    CASE
      {caso_canal}
    END AS canal,
    CASE
      {caso_prio}
      ELSE 99
    END AS prioridad,
    {conteo_dim} AS n_dimensiones
  FROM senales
),
candidatas AS (
  SELECT * FROM evaluadas WHERE regla IS NOT NULL
),
-- Enfriamiento: una segunda alerta sobre alguien que ya está en seguimiento no
-- es información nueva. Se reabre antes de tiempo solo si escala a una regla de
-- mayor prioridad (prioridad menor = regla más precisa).
enfriadas AS (
  SELECT
    candidatas.*,
    LAG(idx_mes)   OVER (PARTITION BY employee_id, canal ORDER BY idx_mes) AS idx_mes_previo,
    LAG(prioridad) OVER (PARTITION BY employee_id, canal ORDER BY idx_mes) AS prioridad_previa
  FROM candidatas
),
vigentes AS (
  SELECT * FROM enfriadas
  WHERE idx_mes_previo IS NULL
     OR idx_mes - idx_mes_previo > CASE canal
           {caso_enfriamiento}
         END
     OR prioridad < prioridad_previa
),
-- Capacidad: el cupo no filtra por estadística, filtra por cuánta conversación
-- puede sostener el equipo. Lo que no entra queda visible, no se borra.
priorizadas AS (
  SELECT
    vigentes.*,
    ROW_NUMBER() OVER (
      PARTITION BY periodo, canal
      ORDER BY {', '.join(op['desempate'])}
    ) AS posicion_en_cola
  FROM vigentes
)
SELECT
  priorizadas.*,
  CASE {caso_cupo}
       ELSE 'lista_seguimiento' END AS estado
FROM priorizadas
ORDER BY periodo DESC, canal, posicion_en_cola
"""


# ---------------------------------------------------------------------------
# Ejecución
# ---------------------------------------------------------------------------

def _explicar(cat: dict, fila: pd.Series) -> tuple[list[str], list[str]]:
    """Traduce las columnas s_* de una fila a texto para un humano.

    La alerta tiene que poder leerse sin la tabla al lado. Cada señal trae su
    plantilla en el YAML y se rellena con los valores de esa persona ese mes.
    """
    etiquetas, detalles = [], []
    for sid, s in cat["senales"].items():
        # Una señal nula no es una señal falsa: es un dato que no tenemos (el
        # CSAT no aplica a roles sin cara al cliente). Ni dispara ni se explica.
        valor = fila.get(f"s_{sid}")
        if pd.isna(valor) or not valor:
            continue
        etiquetas.append(s["etiqueta"])
        try:
            detalles.append(s["explicacion"].format(umbral=s.get("umbral"), **fila.to_dict()))
        except (KeyError, ValueError, TypeError):
            detalles.append(s["etiqueta"])
    return etiquetas, detalles


def ejecutar(cat: dict | None = None, con: duckdb.DuckDBPyConnection | None = None) -> pd.DataFrame:
    cat = cat or cargar()
    con = con or duckdb.connect(str(BD), read_only=True)
    sql = compilar(cat)
    df = con.execute(sql).df()

    reglas = cat["reglas"]
    df["nivel"] = df["regla"].map(lambda r: reglas[r]["nivel"])
    df["regla_nombre"] = df["regla"].map(lambda r: reglas[r]["nombre"])
    df["accion_sugerida"] = df["regla"].map(lambda r: " ".join(reglas[r]["accion_sugerida"].split()))
    df["lectura"] = df["regla"].map(lambda r: " ".join(reglas[r]["lectura"].split()))
    explicado = df.apply(lambda f: _explicar(cat, f), axis=1)
    df["senales"] = [e[0] for e in explicado]
    df["evidencia"] = [e[1] for e in explicado]
    df["destinatario"] = df["canal"].map(
        {c: v["destinatario"] for c, v in cat["operacion"]["canales"].items()})
    df["catalogo_version"] = cat["version"]

    # La garantía estática, comprobada también sobre el resultado.
    minimo = int(df["n_dimensiones"].min())
    if minimo < 2:
        raise CatalogoInvalido(
            f"Se produjo una alerta con {minimo} dimensión. La validación estática "
            "pasó pero el dato dice otra cosa: revisar nulos en las señales."
        )
    return df


def resumen(df: pd.DataFrame, cat: dict) -> None:
    emitidas = df[df.estado.isin(["notificada", "en_panel"])]
    notif = df[df.estado == "notificada"]
    meses = df.periodo.nunique()
    print(f"\nCatálogo v{cat['version']} · {len(cat['reglas'])} reglas · "
          f"{len(cat['senales'])} señales · {len(cat['senales_descartadas'])} descartadas")
    print(f"Candidatas: {len(df):,} en {meses} meses ({len(df)/meses:.1f}/mes) · "
          f"emitidas {len(emitidas):,} ({len(emitidas)/meses:.1f}/mes) · "
          f"en lista de seguimiento {len(df)-len(emitidas):,}")
    print(f"Personas distintas notificadas: {notif.employee_id.nunique():,}")
    print("\nPor canal (emitidas/mes contra su cupo):")
    for canal, c in cat["operacion"]["canales"].items():
        g, cand = emitidas[emitidas.canal == canal], df[df.canal == canal]
        cupo = f"de {c['cupo_mensual']:>3} de cupo" if c["cupo_mensual"] else "sin cupo      "
        print(f"  {canal:<15} {c['modo']:<7} {len(g)/meses:5.1f}/mes {cupo} "
              f"({len(cand)/meses:5.1f} candidatas/mes · {g.employee_id.nunique():,} personas)")
    print("\nPor regla (solo emitidas):")
    for rid, g in emitidas.groupby("regla"):
        r = cat["reglas"][rid]
        print(f"  {rid} · {r['nombre']:<32} {r['nivel']:<5} {len(g)/meses:5.1f}/mes")
    ult = df.periodo.max()
    ultimo = df[df.periodo == ult]
    print(f"\nÚltimo mes ({ult}): "
          f"{len(ultimo[ultimo.estado == 'notificada'])} alertas notificadas, "
          f"{len(ultimo[ultimo.estado == 'en_panel'])} en panel de equidad, "
          f"{len(ultimo[ultimo.estado == 'lista_seguimiento'])} en lista de seguimiento")


def main() -> pd.DataFrame:
    cat = cargar()
    print(f"Validando {CATALOGO.relative_to(RAIZ)} ...")

    SALIDA.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(BD)) as con:
        df = ejecutar(cat, con)
        (SALIDA / "alertas.sql").write_text(compilar(cat), encoding="utf-8")
        # El parquet se escribe con DuckDB, igual que employee_360: una sola
        # dependencia de escritura para todo el pipeline.
        con.register("_alertas", df)
        con.execute("CREATE OR REPLACE TABLE alertas AS SELECT * FROM _alertas")
        con.execute(f"COPY alertas TO '{SALIDA / 'alertas.parquet'}' (FORMAT PARQUET)")

    resumen(df, cat)
    print(f"\nAlertas: {(SALIDA / 'alertas.parquet').relative_to(RAIZ)} · "
          f"SQL: {(SALIDA / 'alertas.sql').relative_to(RAIZ)} · tabla `alertas` en la base")
    return df


if __name__ == "__main__":
    main()
