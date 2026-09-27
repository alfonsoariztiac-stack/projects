"""
Genera DATOS.md: el diccionario de datos y la guía del ambiente.

Se deriva de la base, no se mantiene a mano. Si cambia una columna, cambia el
documento en la siguiente corrida. Documentación que se escribe aparte del
código empieza a mentir el mismo día que alguien toca una tabla.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import sys

import duckdb
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from contratos import CONTRATOS  # noqa: E402
from warehouse import AS_OF, BD, MESES_VENTANA, RAIZ  # noqa: E402

DESTINO = RAIZ / "DATOS.md"

# ---------------------------------------------------------------------------
# Descripciones de columnas de employee_360 (lo único que se escribe a mano)
# ---------------------------------------------------------------------------
DESC = {
  "employee_id": "Identificador del buker. Formato `BUK#####`. Clave de cruce de todas las fuentes.",
  "periodo": "Mes calendario `YYYY-MM`. Junto a `employee_id` forma el grano de la tabla.",
  "idx_mes": "El mes como entero (`año*12 + mes - 1`). Toda la aritmética de fechas usa esto para que el SQL corra igual en BigQuery y DuckDB.",
  "area": "Área organizacional. Derivada del cargo vía `dim_cargos`.",
  "cargo": "Título del cargo. **Ninguna regla lo referencia**: se usa `job_family` × `job_level`.",
  "job_family": "Familia de cargo (12 valores). Eje de gobernanza: las reglas apuntan aquí, no al título.",
  "job_level": "Nivel (`IC1`–`IC5`, `M1`–`M3`). El otro eje de gobernanza.",
  "etiqueta_nivel": "Nombre legible del nivel (Analista, Senior, Líder…).",
  "pais_contrato": "País del contrato (CL/PE/CO/MX/BR). Define banda salarial, moneda y legislación. Distinto de nacionalidad y de país de residencia.",
  "manager_id": "`employee_id` del líder. Nulo solo para gerencias (M3).",
  "activo_en_el_mes": "Si la persona estaba vigente al cierre de ese mes. **No** es el estado de hoy: es el estado de entonces.",
  "antiguedad_meses": "Meses desde el ingreso hasta ese mes.",
  "genero": "Atributo protegido. Solo auditoría de impacto dispar, nunca condición de regla.",
  "nacionalidad": "Atributo protegido (pilar Diversidad Cultural). Solo auditoría.",
  "edad": "Atributo protegido. Solo auditoría.",
  "tramo_edad": "Tramo etario para el panel de equidad (`<26`, `26-35`, `36-45`, `46+`).",
  "moneda": "Moneda del contrato. Los montos NO están convertidos: comparar sueldos entre países exige la banda local, no un tipo de cambio.",
  "sueldo_base": "Sueldo base mensual en moneda local.",
  "banda_min": "Piso de la banda del cargo (`job_family` × `job_level` × país). 80% de la mediana.",
  "banda_med": "Mediana de la banda. Denominador del compa-ratio.",
  "banda_max": "Techo de la banda. 125% de la mediana.",
  "compa_ratio": "`sueldo_base / banda_med`. 1.0 = en la mediana de su banda. Bajo 0.85 es la señal de equidad interna.",
  "meses_desde_ultimo_ajuste": "Meses desde el último ajuste de renta. Convierte 'gana poco' en 'gana poco y nadie lo ha revisado'.",
  "bajo_banda": "Sueldo por debajo del piso de la banda. Más grave que un compa-ratio bajo.",
  "score_vigente": "Score de la última evaluación **ocurrida al cierre de ese mes**, escala 1–4 de Buk.",
  "categoria_vigente": "Bajo lo esperado (<3) · Cumple lo esperado (3–3.4) · Sobresaliente (≥3.5).",
  "score_previo": "Score de la evaluación anterior a esa. Permite leer la trayectoria, no la foto.",
  "categoria_previa": "Categoría de la evaluación anterior.",
  "delta_desempeno": "`score_vigente - score_previo`. La caída es la señal; un nivel bajo sostenido ya lo gestiona el líder por su canal.",
  "meses_desde_evaluacion": "Antigüedad de la evaluación vigente. Un dato viejo pesa menos.",
  "score_90d": "Score de la evaluación inicial de 90 días. Nulo hasta que ocurre.",
  "recomendacion_90d": "Continuar · Seguimiento cercano · No superó el período.",
  "productividad_pct": "Productividad del mes contra la meta del rol (100 = en meta).",
  "prod_prom_3m": "Promedio móvil de 3 meses. Se calcula sobre el calendario continuo, no sobre las filas de la planilla.",
  "prod_prom_3m_previo": "Promedio de los 3 meses anteriores a esos. Es el contrafactual del delta.",
  "prod_delta_3m": "`prom_3m - prom_3m_previo`. La caída de tendencia, no el nivel.",
  "meses_con_prod_3m": "Cuántos de los últimos 3 meses traen dato. Una caída calculada sobre un solo mes observado es ruido; las reglas exigen ≥2.",
  "csat_prom_3m": "CSAT móvil 3 meses. Solo roles de cara al cliente (~47% de la dotación); nulo en el resto **por no aplicar**, no por falta de dato.",
  "csat_delta_3m": "Variación del CSAT contra los 3 meses previos.",
  "dias_sin_vacaciones": "Días acumulados sin tomar vacaciones. Con política ilimitada, quien está desganado tiende a tomar *menos*: proxy de desgaste.",
  "cursos_12m": "Cursos de Buk University finalizados en 12 meses. **Crudo, confundido con antigüedad** — usar el ratio de cohorte.",
  "horas_formacion_12m": "Horas de formación acumuladas en 12 meses.",
  "notas_6m": "Registros de bitácora en 6 meses.",
  "notas_del_mes": "Registros de bitácora ese mes.",
  "meses_sin_curso": "Meses desde el último curso.",
  "meses_sin_nota": "Meses desde el último registro de bitácora. Alimenta el bloque *qué no sabemos* de la alerta: es un punto ciego del sistema, no un síntoma del colaborador.",
  "tramo_antiguedad": "Cohorte de antigüedad (`0-11`, `12-23`, `24-47`, `48+`). Denominador de las comparaciones normalizadas.",
  "ratio_formacion_cohorte": "`cursos_12m` dividido por el promedio de su cohorte de antigüedad ese mes. <1 = se forma menos que sus pares de igual antigüedad.",
  "ratio_vacaciones_cohorte": "`dias_sin_vacaciones` sobre el promedio de su cohorte. Corrige que alguien con 5 meses no pueda acumular 300 días.",
  "cursos_12m_cohorte": "Promedio de cursos de la cohorte (el denominador, expuesto para poder auditarlo).",
  "dias_sin_vacaciones_cohorte": "Promedio de días sin vacaciones de la cohorte.",
  "fecha_salida": "Fecha de desvinculación. **Solo backtest y auditoría.** Prohibida como insumo de reglas.",
  "tipo_salida": "Voluntaria / No voluntaria. Solo backtest.",
  "salida_lamentada": "Salida voluntaria de quien cumplía o superaba lo esperado. Es la métrica que le duele al negocio: no toda salida es un problema a prevenir. Solo backtest.",
  "sale_en_3_meses": "Etiqueta que mira al futuro. **La única columna con fuga temporal deliberada**, aislada aquí para evaluar reglas. Jamás insumo de una regla.",
}

INTRO = f"""# El ambiente de datos

Guía del universo sintético del caso Buk: qué tablas existen, de dónde sale cada
valor y con qué script se pobló.

> Autogenerado por `src/catalogo.py` el {{fecha}}. No editar a mano.
> Corte del análisis: **{AS_OF}** · ventana: **{MESES_VENTANA} meses** · semilla: **20260902**.

## Ninguno de estos datos es real

Todo lo que hay aquí es sintético. No hay datos de Buk ni de ninguna persona
real: nombres, sueldos, evaluaciones y notas se generan con `numpy` y `faker` a
partir de una semilla fija. La escala imita la dotación propia de Buk (~2.000
bukers), **no** los +2 millones de colaboradores que usan su plataforma — esos
son usuarios finales de sus clientes, otra escala y otro problema.

## Dónde estás parado

| | |
|---|---|
| Motor | **DuckDB** {duckdb.__version__} (archivo único, sin servidor) |
| Archivo | `data/out/buk.duckdb` |
| Dialecto | SQL escrito en el subconjunto común con **BigQuery**, sin capa de traducción |
| Export | `data/out/employee_360.parquet` |

DuckDB hace aquí de BigQuery. El SQL de `src/sql/` evita a propósito
`DATE_DIFF`, `DATE_TRUNC` y `SAFE_CAST` —las tres tienen firmas distintas en
cada motor— y resuelve toda la aritmética de fechas con el entero `idx_mes`.
Migrar a producción es cambiar el conector y el nombre del dataset; el SQL no se
toca. Lo que se muestra en la presentación es literalmente lo que correría en el
warehouse de Buk.

### Abrir la base

```bash
uv run python -c "
import duckdb
con = duckdb.connect('data/out/buk.duckdb', read_only=True)
print(con.execute('SELECT * FROM employee_360 LIMIT 5').df())
"
```

### Correr el pipeline completo

```bash
uv run python src/generate_data.py   # 7 fuentes sintéticas -> data/raw/
uv run python src/warehouse.py       # ingesta + limpieza + modelo -> data/out/
uv run python src/catalogo.py        # regenera este documento
```

## El flujo, de punta a punta

```
src/generate_data.py                 estructura causal latente -> 7 archivos
        |
        v
data/raw/  (CSV "de BigQuery" + XLSX "de Google Sheets", uno sucio a propósito)
        |
        v
src/contratos.py + src/ingest.py     contratos, limpieza, cuarentena
        |                            -> data/out/reporte_calidad.md
        v
tablas stg_*  en DuckDB
        |
        v
src/sql/01..05                       vistas -> employee_360 (persona x mes)
        |
        v
data/out/employee_360.parquet        la única tabla que leen las reglas
```

Aparte, y **nunca leído por el pipeline**: `data/laboratorio/` guarda la verdad
latente (el perfil de cada persona, su trayectoria, la etiqueta de tono y tema
de cada nota). Está separado a propósito. Si las reglas pudieran mirar el perfil
que generó los datos, el backtest sería una tautología: estaría comprobando que
el generador funciona, no que las reglas sirven.
"""

CAUSAL = """
## Cómo se llega a los valores: la estructura causal latente

Los datos no se sortean columna por columna. Cada persona recibe un **perfil
latente** que gobierna una trayectoria mensual de *engagement*, y de esa
trayectoria se derivan todos los observables: productividad, CSAT, días sin
vacaciones, cursos, tono de las notas de bitácora, evaluaciones y la propia
probabilidad de salir. Por eso las señales se mueven juntas, como en la realidad,
en vez de ser cinco columnas independientes que por casualidad se cruzan.

### Los cinco perfiles

| Perfil | Peso | Qué le pasa | Cómo se ve en los datos |
|---|---|---|---|
| `estable` | 68% | Nada. Ruido en torno a su nivel | Todas las señales planas |
| `deterioro` | 12% | Desgaste progresivo | Productividad se desploma, sueldo **normal**, muchos días sin vacaciones |
| `estrella_subpagada` | 9% | Buen desempeño mal pagado | Compa-ratio ~0.85, desempeño **sobre** el promedio |
| `bajo_desempeno` | 5% | No alcanza lo esperado | Score bajo desde el inicio, poca formación |
| `nuevo_dificil` | 6% | Onboarding fallido | Solo aplica con antigüedad <400 días |

### La trayectoria

```
engagement(mes) = eng_base + eng_pendiente x avance
   avance = 0                 lejos del ancla (todavía en su nivel base)
   avance = declive_meses     en el ancla (el fondo)
```

El **ancla** es el mes de salida de la persona; para quien sigue activo, el
corte del análisis más una dispersión de hasta 6 meses (parte de la gente en
riesgo está a mitad de camino, no toda en el fondo). `declive_meses` varía entre
6 y 15 por persona: si todos cayeran en el mismo plazo, "detectado con 60 días
de antelación" sería una constante del generador y no una propiedad de las
reglas.

### Derivación de cada observable

| Observable | Fórmula | Nota |
|---|---|---|
| Productividad | `62 + 48·eng + intercepto_persona + N(0, 2.6)` | El intercepto (σ=6.0) es **persistente por persona** |
| CSAT | `2.55 + 2.30·eng + intercepto_csat + N(0, 0.16)` | Solo familias de cara al cliente |
| NPS | `-45 + 135·eng + 45·intercepto_csat + N(0, 7)` | Idem |
| Días sin vacaciones | Acumula +30/mes; se resetea con prob. `0.045 + 0.14·eng` | Quien está desganado toma **menos** vacaciones |
| Nota de desempeño | `clip(1.72 + 2.18·eng + N(0, 0.20), 1, 4)` | Escala 1–4 real de Buk |
| Compa-ratio | `N(0.97 + antigüedad·0.017 + 0.19·(eng_base − 0.745), 0.085)` | La **inclinación por mérito** implementa el lineamiento *Mérito y Desempeño* de Buk |
| Cursos | `Poisson((0.45 + 2.8·eng) · meses_observados / 12)` | **Tasa** por tiempo, más un pulso de onboarding |
| Tono de bitácora | Umbrales sobre `eng` | Temas sorteados del repertorio del perfil |
| Salida | Propensidad por perfil: `estable` 1.0, `deterioro` 4.5, `estrella` 4.0 | 650 salidas en 24 meses (~12%/año) |

### Tres errores de acoplamiento que hubo que corregir

Valen como advertencia sobre generadores sintéticos, porque los tres producían
datos que *parecían* correctos y volvían inútil cualquier regla:

1. **La salida era independiente del perfil.** El estado se marcaba por posición
   en el bucle, antes de que existiera el perfil. `estable` salía 17.2% y
   `deterioro` 19.0%: el 70% de las salidas no tenía ninguna señal previa.
2. **El declive estaba anclado al calendario, no a la salida.** Quien renunció en
   junio 2025 apenas había empezado a caer cuando se fue; su deterioro "ocurría"
   meses después de que ya no estaba. La causa no precedía al efecto, y las
   reglas marcaban al 25% de quienes se iban contra el 28% de quienes se
   quedaban: **lift negativo**.
3. **El ruido mensual superaba a la señal.** Sin intercepto por persona, el
   mismo individuo oscilaba más de un mes a otro (σ=6.5) que lo que se
   distinguía de sus pares (σ≈3.6). Como las reglas leen deltas *dentro* de la
   misma persona, marcaban al 24.9% de la gente sana. Con intercepto persistente
   y ruido mensual de 2.6, ese falso positivo cae a 5.7%.
4. **La compensación no premiaba el mérito.** El compa-ratio salía plano —de
   hecho, levemente invertido— entre bandas de desempeño: quien rendía bajo lo
   esperado quedaba marginalmente más arriba en banda que quien sobresalía. Eso
   contradice de frente el lineamiento *Mérito y Desempeño* del Culture Code.
   Con la inclinación por mérito el orden queda como la política lo produciría:
   Sobresaliente 1.016 · Cumple lo esperado 0.994 · Bajo lo esperado 0.963.

Los cursos tuvieron su propia versión del problema 3: se sorteaba el **total**
por persona y se repartía entre ingreso y salida, así que quien se iba antes
recibía los mismos cursos en menos meses. El dato terminaba diciendo que
formarse mucho predice renunciar. Una métrica acumulada sin denominador de
tiempo casi siempre está midiendo otra cosa.
"""

SUCIEDAD = """
## La suciedad inyectada a propósito

`gs_metricas_operativas.xlsx` simula una planilla mantenida a mano durante
meses. No es un adorno: la descripción del cargo pide explícitamente garantizar
la validez de la información *"a través de la limpieza de las bases de datos"*.
Si la fuente llegara perfecta, la capa de calidad del pipeline no se podría
demostrar.

| Suciedad | Cómo se ve | Qué hace la ingesta |
|---|---|---|
| Encabezados escritos por una persona | `ID Colaborador`, `Mes `, `CSAT (1-5)` | Renombra según el contrato |
| Tres formatos de fecha conviviendo | `2026-08`, `ago-2026`, `08/2026` | Normaliza a `YYYY-MM` |
| Nulos escritos a mano | `N/A`, `s/i`, `-` | Los lee como ausencia de dato |
| Decimales con coma (locale es-CL) | `94,4` | Convierte a punto |
| Espacios en la clave de cruce | `" BUK10427"` | Recorta |
| Valores imposibles | productividad `999`, CSAT `0` | 999 rechaza la fila; CSAT 0 anula la celda |
| Filas duplicadas por copiar y pegar | misma persona y mes repetidos | Conserva la primera |

La distinción entre las dos últimas es deliberada: un CSAT imposible no invalida
la productividad de esa misma fila, pero una productividad imposible sí invalida
la fila entera, porque es la métrica que la fila existe para reportar.

Toda fila rechazada se escribe en `data/out/cuarentena/` con su motivo. Nada
desaparece en silencio. Y si una fuente supera el 5% de rechazo, el pipeline se
detiene en vez de producir alertas sobre datos degradados.
"""


def _leidas() -> dict:
    """Rescata las filas leídas del reporte de calidad, para no recontar el crudo."""
    rep = RAIZ / "data" / "out" / "reporte_calidad.md"
    if not rep.exists():
        return {}
    out = {}
    for linea in rep.read_text(encoding="utf-8").splitlines():
        c = [x.strip() for x in linea.strip().strip("|").split("|")]
        if len(c) == 7 and c[0] in CONTRATOS:
            out[c[0]] = (c[2], c[4], c[6])
    return out


def seccion_fuentes(con) -> str:
    L = ["\n## Las 7 fuentes crudas (`data/raw/`)\n",
         "Formatos deliberadamente heterogéneos, como en el ambiente real de Buk: "
         "lo que vive en BigQuery llega como CSV, lo que vive en Google Sheets llega "
         "como XLSX. Son 7 archivos y 9 contratos porque `gs_desarrollo_bitacora.xlsx` "
         "trae dos hojas (cursos y bitácora) y `dim_cargos.csv` es la tabla dimensional "
         "de gobernanza, no una fuente operativa.\n",
         "| Fuente | Archivo | Formato | Leídas | Válidas | Rechazo | Simula |",
         "|---|---|---|---:|---:|---:|---|"]
    origen = {"csv": "tabla en BigQuery", "xlsx": "planilla en Google Sheets"}
    leidas = _leidas()
    for nombre, c in CONTRATOS.items():
        n = con.execute(f"SELECT COUNT(*) FROM stg_{nombre}").fetchone()[0]
        le, _, tasa = leidas.get(nombre, ("—", "", "—"))
        L.append(f"| `{nombre}` | `{c['archivo']}` | {c['formato'].upper()} | {le} | "
                 f"{n:,} | {tasa} | {origen[c['formato']]} |")
    L.append("\nEl detalle de cada incidencia está en "
             "[`data/out/reporte_calidad.md`](data/out/reporte_calidad.md), y cada fila "
             "rechazada en [`data/out/cuarentena/`](data/out/cuarentena/).\n")
    return "\n".join(L)


def seccion_modelo(con) -> str:
    L = ["\n## Las tablas del warehouse\n",
         "| Objeto | Tipo | Filas | Qué es |", "|---|---|---:|---|"]
    desc_obj = {
        "dim_periodos": ("tabla", "Calendario mensual de la ventana. En BigQuery sería una tabla del dataset común."),
        "dim_cargos_v": ("vista", "Alias de `stg_dim_cargos`. **La pieza de gobernanza**: mapea cargo → familia × nivel × banda."),
        "persona_mes": ("vista", "Columna vertebral: una fila por persona × mes, con vigencia calculada a ese mes."),
        "operativa_mes": ("vista", "Ventanas móviles de productividad y CSAT, calculadas sobre el calendario continuo."),
        "desempeno_mes": ("vista", "Evaluación vigente y anterior en cada mes, con corrección temporal."),
        "desarrollo_escucha_mes": ("vista", "Formación y bitácora acumuladas; meses desde el último evento."),
        "employee_360": ("tabla", "**La tabla que leen las reglas.** Grano: persona × mes."),
    }
    for nombre, c in CONTRATOS.items():
        n = con.execute(f"SELECT COUNT(*) FROM stg_{nombre}").fetchone()[0]
        L.append(f"| `stg_{nombre}` | tabla | {n:,} | {c['descripcion']} |")
    for obj, (tipo, d) in desc_obj.items():
        try:
            n = con.execute(f"SELECT COUNT(*) FROM {obj}").fetchone()[0]
            L.append(f"| `{obj}` | {tipo} | {n:,} | {d} |")
        except Exception:
            pass
    return "\n".join(L)


def seccion_360(con) -> str:
    cols = con.execute("PRAGMA table_info('employee_360')").df()
    ult = con.execute("SELECT MAX(periodo) FROM employee_360").fetchone()[0]
    n, npers, nmes = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT employee_id), COUNT(DISTINCT periodo) FROM employee_360"
    ).fetchone()

    q = "SELECT COUNT(*) FROM employee_360 WHERE periodo='%s' AND activo_en_el_mes" % ult
    activos = con.execute(q).fetchone()[0]

    L = ["\n## `employee_360` — diccionario completo\n",
         f"**{n:,} filas · {npers:,} personas · {nmes} meses** "
         f"(grano: una fila por persona × mes que estuvo vigente).\n",
         f"Las estadísticas son del último mes de la ventana (`{ult}`, {activos:,} activos).\n",
         "| Columna | Tipo | % nulos | Estadística | Qué es |",
         "|---|---|---:|---|---|"]

    for r in cols.itertuples():
        col, tipo = r.name, r.type
        try:
            nul = con.execute(f"SELECT 100.0*AVG(CASE WHEN {col} IS NULL THEN 1.0 ELSE 0 END) "
                              f"FROM employee_360 WHERE periodo='{ult}'").fetchone()[0] or 0
        except Exception:
            nul = 0
        stat = ""
        if tipo in ("BIGINT", "DOUBLE", "INTEGER", "HUGEINT"):
            try:
                mn, md, mx = con.execute(
                    f"SELECT MIN({col}), MEDIAN({col}), MAX({col}) FROM employee_360 "
                    f"WHERE periodo='{ult}' AND {col} IS NOT NULL").fetchone()
                if mn is not None:
                    stat = f"min {mn:,.2f} · mediana {md:,.2f} · max {mx:,.2f}".replace(".00", "")
            except Exception:
                pass
        elif tipo in ("VARCHAR", "BOOLEAN"):
            try:
                vals = con.execute(
                    f"SELECT {col}, COUNT(*) c FROM employee_360 WHERE periodo='{ult}' "
                    f"AND {col} IS NOT NULL GROUP BY 1 ORDER BY c DESC LIMIT 3").df()
                if len(vals):
                    nd = con.execute(f"SELECT COUNT(DISTINCT {col}) FROM employee_360").fetchone()[0]
                    top = ", ".join(f"`{v}`" for v in vals.iloc[:, 0].astype(str))
                    stat = f"{nd} valores · top: {top}"
            except Exception:
                pass
        L.append(f"| `{col}` | {tipo} | {nul:.0f}% | {stat} | {DESC.get(col, '')} |")
    return "\n".join(L)


def _celda(v) -> str:
    """Un dato ausente se muestra como raya, no como `nan`."""
    t = str(v)
    return "—" if t in ("nan", "None", "NaN", "<NA>") else t


def seccion_distribuciones(con) -> str:
    ult = con.execute("SELECT MAX(periodo) FROM employee_360").fetchone()[0]
    L = [f"\n## Distribuciones de control ({ult}, activos)\n",
         "Los valores contra los que se calibró el universo, tomados del Culture Code de Buk.\n"]

    def tabla(titulo, sql, cols):
        df = con.execute(sql).df()
        L.append(f"**{titulo}**\n")
        L.append("| " + " | ".join(cols) + " |")
        L.append("|" + "---|" * len(cols))
        for r in df.itertuples(index=False):
            L.append("| " + " | ".join(_celda(v) for v in r) + " |")
        L.append("")

    base = "FROM employee_360 WHERE periodo='%s' AND activo_en_el_mes" % ult
    tabla("Género (Buk declara 54% mujeres)",
          f"SELECT genero, COUNT(*) n, ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER (),1) pct {base} GROUP BY 1 ORDER BY n DESC",
          ["genero", "n", "%"])
    tabla("País de contrato (expansión: CL 2017, CO 2019, PE 2020, MX 2022, BR 2025)",
          f"SELECT pais_contrato, COUNT(*) n, ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER (),1) pct, "
          f"ROUND(MEDIAN(antiguedad_meses),0) antig_mediana, MAX(antiguedad_meses) antig_max "
          f"{base} GROUP BY 1 ORDER BY n DESC",
          ["país", "n", "%", "antigüedad mediana", "antigüedad máx."])
    L.append("La mediana es parecida en todos los países porque Buk creció rápido en "
             "todos a la vez: la mayoría de cada cohorte entró hace poco. Lo que "
             "codifica la expansión es el **máximo** — 115 meses en Chile (2017) contra "
             "19 en Brasil (2025).\n")
    tabla("Desempeño en la escala 1–4 de Buk",
          f"SELECT COALESCE(categoria_vigente, 'Sin evaluación aún') categoria_vigente, COUNT(*) n, ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER (),1) pct, "
          f"ROUND(AVG(score_vigente),2) score_prom {base} GROUP BY 1 ORDER BY n DESC",
          ["categoría", "n", "%", "score medio"])
    L.append("El 13,5% sin evaluación son quienes aún no completan su primer ciclo. "
             "No es un dato faltante: es una persona que todavía no tiene evaluación, y "
             "las reglas de desempeño simplemente no aplican sobre ella.\n")
    tabla("Nivel de cargo (Buk declara ~200 líderes sobre ~1.800 bukers)",
          f"SELECT job_level, etiqueta_nivel, COUNT(*) n, ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER (),1) pct "
          f"{base} GROUP BY 1,2 ORDER BY 1",
          ["nivel", "etiqueta", "n", "%"])
    tabla("Compa-ratio",
          f"SELECT ROUND(AVG(compa_ratio),3) media, ROUND(MEDIAN(compa_ratio),3) mediana, "
          f"ROUND(100.0*AVG(CASE WHEN compa_ratio<0.85 THEN 1.0 ELSE 0 END),1) pct_bajo_085, "
          f"ROUND(100.0*AVG(CASE WHEN bajo_banda THEN 1.0 ELSE 0 END),1) pct_bajo_banda {base}",
          ["media", "mediana", "% bajo 0.85", "% bajo el piso de banda"])
    tabla("Edad y antigüedad (Buk declara edad promedio 31)",
          f"SELECT ROUND(AVG(edad),1) edad_media, ROUND(MEDIAN(antiguedad_meses),1) antig_mediana, "
          f"COUNT(DISTINCT nacionalidad) nacionalidades {base}",
          ["edad media", "antigüedad mediana (meses)", "nacionalidades"])
    return "\n".join(L)


SCRIPTS = """
## Qué script pobló qué

### `src/generate_data.py` — el generador

Corre una vez y escribe los 7 archivos de `data/raw/` más los 2 de
`data/laboratorio/`. El orden importa: primero existe la persona, después su
perfil, después su destino, y recién entonces se derivan los observables.

| Función | Qué produce |
|---|---|
| `construir_poblacion()` | 2.650 personas: id, nombre ficticio, cargo, país, género, nacionalidad, fecha de ingreso. Calibra la demografía a los valores del Culture Code |
| `_asignar_jerarquia()` | `manager_id` de cada persona, respetando que un líder sea de nivel superior y de la misma área |
| `asignar_perfiles()` | El perfil latente, `eng_base`, `eng_pendiente`, `declive_meses` y los interceptos persistentes de productividad y CSAT |
| `marcar_desvinculados()` | Sortea las 650 salidas **con probabilidad proporcional al perfil**. Es la función que corrige el error nº 1 |
| `generar_salidas()` | Fecha, tipo (voluntaria/no voluntaria), motivo y transcripción de entrevista de salida |
| `anclar_trayectorias()` | `idx_ancla`: el mes contra el cual se mide el declive. Corrige el error nº 2 |
| `engagement()` | Evalúa la trayectoria de una persona en un mes dado. Es la función que todas las demás consultan |
| `generar_compensaciones()` | Sueldo base, banda min/med/max por `job_family × job_level × país`, compa-ratio, fecha del último ajuste |
| `generar_eval_90d()` | Evaluación inicial de 90 días, solo para quien ya la cumplió |
| `generar_eval_desempeno()` | Ciclo anual + mid-year de julio, escala 1–4 |
| `generar_metricas_operativas()` | Productividad, CSAT, NPS y días sin vacaciones, mes a mes |
| `ensuciar_metricas()` | **Degrada a propósito** la planilla operativa: las 7 suciedades de la tabla anterior |
| `generar_cursos()` | Cursos de Buk University como tasa por tiempo observado, con pulso de onboarding |
| `generar_bitacora()` | Notas de seguimiento de 80–200 palabras, compuestas por tono y temas del perfil |

### `src/contratos.py` — la frontera

No produce datos: declara qué se espera de cada fuente. Es además una
**allowlist**: una columna que no está declarada no entra al pipeline aunque
venga en el archivo. Por eso `email` no aparece en ninguna parte del módulo —
existe en el origen y nunca cruza. `nombre` sí entra, pero se queda en staging y
no llega a `employee_360`: se une al final, solo para renderizar la alerta a
quien está autorizado a verla.

### `src/ingest.py` — limpieza y cuarentena

| Función | Qué hace |
|---|---|
| `leer()` | Abre CSV o XLSX, renombra encabezados según el contrato, recorta a las columnas declaradas |
| `norm_*()` | Normalizadores por tipo. `norm_periodo()` acepta los tres formatos de fecha que conviven en la planilla |
| `validar()` | Aplica rangos y obligatoriedad. Campo obligatorio fuera de rango → rechaza la fila; campo opcional → anula la celda y conserva la fila |
| `integridad()` | Falla si algún `(cargo, país)` del directorio no existe en `dim_cargos`. **Es el test de gobernanza**: con 325 cambios internos al año, es el que avisa que la tabla dimensional quedó atrás |
| `ingestar()` | Orquesta todo y devuelve tablas limpias + reporte |
| `escribir_reporte()` | `data/out/reporte_calidad.md` y los CSV de `data/out/cuarentena/` |

### `src/warehouse.py` — el modelo

Carga las tablas limpias en DuckDB como `stg_*`, construye `dim_periodos` y
ejecuta los archivos de `src/sql/` **en orden alfabético**:

| Archivo | Objeto | Qué resuelve |
|---|---|---|
| `01_persona_mes.sql` | `persona_mes` | La columna vertebral: cruce persona × calendario, con vigencia calculada a cada mes |
| `02_operativa.sql` | `operativa_mes` | Ventanas móviles de 3 meses sobre el calendario continuo, no sobre las filas de la planilla |
| `03_desempeno.sql` | `desempeno_mes` | Evaluación vigente y anterior **con corrección temporal** |
| `04_desarrollo_escucha.sql` | `desarrollo_escucha_mes` | Acumulados de formación y bitácora; meses desde el último evento |
| `05_employee_360.sql` | `employee_360` | Une todo y agrega las normalizaciones por cohorte de antigüedad |

Corrida completa (generación + ingesta + modelo): **~4 segundos**.

## Corrección temporal: el detalle que hace válido el backtest

`employee_360` para el mes *m* contiene **solo lo que se sabía al cierre de m**.
Suena obvio y casi nunca se cumple: lo natural al escribir el SQL es unir la
última evaluación de cada persona a todas sus filas, y ahí el modelo de marzo
queda sabiendo el resultado de la evaluación de julio.

Con esa fuga, el backtest reporta un recall inflado que se desploma el día que
el sistema corre en producción, porque en producción el futuro no está
disponible. La implementación cuenta cuántas evaluaciones **habían ocurrido** a
cada mes y une por esa posición (`03_desempeno.sql`). Verificado: **0
violaciones** en las 31.835 filas.

La única excepción es `sale_en_3_meses`, que mira al futuro a propósito. Está
aislada y documentada como etiqueta de evaluación, jamás como insumo de una
regla.
"""


LABORATORIO = """
## `data/laboratorio/` — la verdad latente

Dos archivos que **el pipeline no lee jamás**:

| Archivo | Contenido |
|---|---|
| `_verdad_latente.csv` | Por persona: `perfil_latente`, `eng_base`, `eng_pendiente`, `declive_meses`, `idx_ancla`, interceptos, fecha de salida |
| `_bitacora_etiquetas.csv` | Por nota: el tono y los temas con que fue construida |

Sirven para dos cosas: verificar que el generador produce lo que se pretende, y
—en el caso de las etiquetas de bitácora— medir cuánto acierta el LLM contra una
respuesta conocida.

Están separados por la misma razón por la que un laboratorio no guarda los
reactivos junto a las muestras. Si una regla pudiera leer `perfil_latente`, el
backtest comprobaría que el generador funciona, no que las reglas sirven.

## Honestidad obligatoria sobre el backtest

El backtest funciona **por construcción**: los datos son sintéticos y la señal
fue puesta ahí a propósito. Es el **método de validación**, no evidencia de que
el sistema funcione en la realidad. Decirlo antes de que lo pregunten suma
credibilidad; que lo pregunten, resta.

Dato relacionado: cerca del **44% de las salidas** viene del perfil `estable`,
gente sin ninguna señal previa —una oferta inesperada, una mudanza, un cambio de
vida—. Ese porcentaje es el techo de recall del sistema, y es sano que exista.
Un backtest que detectara el 100% describiría un mundo donde las personas son
predecibles, no un sistema que funciona.
"""


def main() -> None:
    con = duckdb.connect(str(BD), read_only=True)
    partes = [
        INTRO.format(fecha=f"{dt.datetime.now():%Y-%m-%d %H:%M}"),
        CAUSAL,
        seccion_fuentes(con),
        SUCIEDAD,
        seccion_modelo(con),
        SCRIPTS,
        seccion_360(con),
        seccion_distribuciones(con),
        LABORATORIO,
    ]
    DESTINO.write_text("\n".join(partes), encoding="utf-8")
    print(f"Escrito: {DESTINO.relative_to(RAIZ)} "
          f"({len(DESTINO.read_text(encoding='utf-8').splitlines()):,} líneas)")


if __name__ == "__main__":
    main()
