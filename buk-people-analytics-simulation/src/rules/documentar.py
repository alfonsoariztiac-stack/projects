"""
Genera REGLAS.md: el documento de gobernanza del catálogo de alertas.

Hermano de `catalogo.py`, misma tesis: no se mantiene a mano. Un catálogo de
reglas que decide sobre personas necesita un documento que un comité pueda
leer sin abrir el YAML ni el SQL — y ese documento deja de servir el día que
se desalinea del código. Aquí se deriva de las tres fuentes que ya existen:

    reglas.yaml   qué decidimos y por qué           (la norma)
    backtest.py   qué produce esa decisión          (la evidencia)
    equidad.py    sobre quién cae                   (el contrapeso)

Si alguien cambia un umbral y no vuelve a correr esto, el documento no queda
desactualizado: queda ausente. Es deliberado.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import sys

import duckdb
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import equidad  # noqa: E402
from backtest import (VENTANA_MESES, _preparar, cobertura_panel_desarrollo,  # noqa: E402
                      curva_de_calibracion, lift_por_senal, metricas, techo_de_cobertura)
from motor import CONTEXTO, cargar, columnas_leidas, condicion_regla  # noqa: E402
from warehouse import BD, RAIZ  # noqa: E402

DESTINO = RAIZ / "REGLAS.md"


def _md(df: pd.DataFrame, decimales: int = 2) -> str:
    """DataFrame a tabla markdown. A mano: no vale una dependencia más."""
    def celda(v):
        if pd.isna(v):
            return "n/d"
        if isinstance(v, float):
            return f"{v:,.{decimales}f}"
        return str(v)
    cab = "| " + " | ".join(str(c) for c in df.columns) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    filas = ["| " + " | ".join(celda(v) for v in f) + " |"
             for f in df.itertuples(index=False)]
    return "\n".join([cab, sep, *filas])


def _tabla(df: pd.DataFrame, columnas: dict[str, str], decimales: int = 2) -> str:
    """DataFrame a markdown, con nombres de columna legibles por humanos."""
    return _md(df[list(columnas)].rename(columns=columnas), decimales)


def _parrafo(texto: str) -> str:
    """Los bloques del YAML vienen con saltos de línea de edición; se aplanan."""
    return " ".join((texto or "").split())


# ---------------------------------------------------------------------------

def encabezado(cat: dict) -> str:
    op = cat["operacion"]
    return f"""# Catálogo de alertas de retención · v{cat['version']}

> Generado por `src/rules/documentar.py` el {dt.datetime.now():%Y-%m-%d %H:%M}.
> No editar a mano: la fuente de verdad es `src/rules/reglas.yaml`.

| | |
|---|---|
| **Versión** | {cat['version']} |
| **Vigente desde** | {cat['vigente_desde']} |
| **Dueño** | {cat['duenio']} |
| **Ciclo de revisión** | {cat['ciclo_revision']} |
| **Frecuencia de corrida** | {op['frecuencia']} |
| **Retención de alertas** | {op['retencion_dias']} días |

## Qué decide este sistema

{_parrafo(cat['objetivo'])}

**Y qué no decide.** Una alerta es una invitación a conversar, no un juicio.
No entra a ningún proceso de desempeño, no cambia la evaluación de nadie y no
llega a quien decide sobre la carrera de la persona alertada.

Nunca recibe una alerta: {', '.join(f'**{x}**' for x in op['nunca_recibe'])}.

## Universo

Se evalúa `{cat['universo']['tabla']}` bajo la condición
`{cat['universo']['condicion']}`.

{_parrafo(cat['universo']['justificacion'])}
"""


def garantias(cat: dict) -> str:
    prohibidos = ", ".join(f"`{a}`" for a in cat["atributos_prohibidos"])
    n_leidas = len(columnas_leidas(cat))
    return f"""
## Garantías verificadas en código

Estas no son promesas del documento: son seis validaciones que corren antes de
compilar el SQL. Si alguna falla, `motor.py` levanta `CatalogoInvalido` y no se
emite ninguna alerta. Un catálogo inválido no produce alertas malas — no
produce ninguna.

| # | Garantía | Por qué |
|---|---|---|
| 1 | Ninguna expresión menciona un atributo prohibido | La prohibición se verifica, no se confía |
| 2 | Toda señal referida por una regla existe en el catálogo | Una regla que apunta al vacío no falla: no dispara nunca, en silencio |
| 3 | **Toda rama de toda regla cruza ≥ 2 dimensiones** | Una sola dimensión es una métrica, no una lectura de una persona |
| 4 | Toda rama contiene ≥ 1 señal de tipo `riesgo` | Impide una alerta armada solo con contexto |
| 5 | Todo canal usado por una regla tiene capacidad declarada | Una alerta sin destinatario ni cupo es una alerta que nadie atiende |
| 6 | Las prioridades son únicas | La cola tiene que ser determinista para poder auditarse |

### Atributos prohibidos

{prohibidos}

No pueden aparecer en ninguna expresión de señal ni condición de regla. Sí se
miden en la auditoría de impacto dispar: la prohibición se paga con la
obligación de vigilar.

### Lista blanca de lectura

El SQL proyecta **{n_leidas} columnas**, derivadas de las expresiones de las
señales más el contexto que la alerta necesita para explicarse. No es una lista
mantenida aparte: se calcula desde el catálogo. Lo que ninguna señal menciona,
no se selecciona — y por eso las etiquetas de salida (`fecha_salida`,
`sale_en_3_meses`) no pueden filtrarse aunque alguien las escriba por error.
"""


def senales(cat: dict, lift: pd.DataFrame) -> str:
    partes = ["\n## Dimensiones\n",
              "| Dimensión | Qué observa |", "|---|---|"]
    partes += [f"| `{k}` | {v} |" for k, v in cat["dimensiones"].items()]

    partes.append("\n## Señales vigentes\n")
    partes.append("Una señal de tipo `contexto` no puede fundar una alerta por sí sola: "
                  "sirve para completar la segunda dimensión de una regla. "
                  "`desempeno_sobresaliente` es contexto — nunca alerta a nadie, "
                  "pero cambia por completo la lectura de un sueldo bajo banda.\n")
    partes += ["| Señal | Dimensión | Tipo | Condición | Lift |", "|---|---|---|---|---|"]
    l = lift.set_index("senal") if "senal" in lift.columns else lift
    for sid, s in cat["senales"].items():
        expr = s["expr"].format(umbral=s.get("umbral", ""))
        medido = s.get("lift_medido")
        partes.append(f"| `{sid}` | {s['dimension']} | {s['tipo']} | `{expr}` | "
                      f"{medido if medido else '—'} |")

    partes.append("\n### Por qué cada señal está aquí\n")
    for sid, s in cat["senales"].items():
        if s.get("justificacion"):
            partes.append(f"**`{sid}` — {s['etiqueta']}**  \n{_parrafo(s['justificacion'])}\n")
    return "\n".join(partes)


def descartes(cat: dict) -> str:
    partes = ["""
## Señales descartadas

La sección más importante del catálogo. Documenta lo que se probó y se sacó, con
el número que lo justifica. Un catálogo que solo muestra lo que quedó no permite
distinguir un diseño de una colección de intuiciones que sobrevivieron.

La columna que decide es **lift sobre salida lamentada**. `lift ≈ 1` significa
indistinguible del azar; `lift < 1` significa que la señal predice lo contrario
de lo que buscamos.
""",
              "| Señal | Condición | Lift lamentada | Lift cualquier salida |",
              "|---|---|---|---|"]
    for d in cat["senales_descartadas"]:
        otro = d.get("lift_salida_cualquiera", "—")
        partes.append(f"| `{d['id']}` | `{d['expr']}` | **{d['lift_salida_lamentada']}** | {otro} |")
    partes.append("")
    for d in cat["senales_descartadas"]:
        partes.append(f"**`{d['id']}`**  \n{_parrafo(d['motivo'])}\n")
    return "\n".join(partes)


def reglas(cat: dict) -> str:
    partes = ["""
## Reglas vigentes

El orden de prioridad no es una opinión sobre qué duele más: es el ranking de
precisión medida en el backtest. Se recalcula en cada revisión trimestral, y una
regla puede bajar de puesto sin que nadie la haya cambiado.
""",
              "| # | Regla | Canal | Nivel | Condición |", "|---|---|---|---|---|"]
    for rid, r in sorted(cat["reglas"].items(), key=lambda kv: kv[1]["prioridad"]):
        cond = condicion_regla(cat, rid).replace("|", "\\|")
        partes.append(f"| {r['prioridad']} | **{rid}** {r['nombre']} | {r['canal']} | "
                      f"{r['nivel']} | `{cond}` |")

    partes.append("\n### Qué dice cada regla y qué se hace con ella\n")
    for rid, r in sorted(cat["reglas"].items(), key=lambda kv: kv[1]["prioridad"]):
        partes.append(f"**{rid} · {r['nombre']}**  \n"
                      f"*Lectura:* {_parrafo(r['lectura'])}  \n"
                      f"*Acción sugerida:* {_parrafo(r['accion_sugerida'])}\n")
    return "\n".join(partes)


def operacion(cat: dict) -> str:
    op = cat["operacion"]
    filas = []
    for nombre, c in op["canales"].items():
        cupo = c["cupo_mensual"] if c["cupo_mensual"] is not None else "sin tope"
        enf = f"{c['enfriamiento_meses']} meses" if c["enfriamiento_meses"] else "sin enfriamiento"
        filas.append(f"| `{nombre}` | {c['modo']} | {cupo} | {enf} | {c['destinatario']} |")
    return f"""
## Operación

La distinción que ordena todo el bloque es **evento vs estado**.

Un evento —la productividad cayó, la evaluación bajó— pasó una vez y hay una
ventana para reaccionar. Repetirlo cada mes no agrega información y quema la
atención de quien lo recibe: por eso lleva enfriamiento y tope de capacidad.

Un estado —está pagado bajo el piso de su banda— es cierto hoy y lo seguirá
siendo mañana hasta que alguien lo arregle. Ponerle enfriamiento sería dejar de
mirar un problema que no se movió. Va a un panel que se lee entero, sin tope:
un panel no consume atención por caso.

| Canal | Modo | Cupo mensual | Enfriamiento | Destinatario |
|---|---|---|---|---|
{chr(10).join(filas)}

**Desempate de la cola:** {', '.join(f'`{d}`' for d in op['desempate'])}.

El enfriamiento tiene una excepción: si la persona reaparece por una regla de
**mayor** prioridad, la alerta pasa igual. Silenciar una escalada sería el peor
efecto posible de un mecanismo pensado para reducir ruido.
"""


def panel_desarrollo(panel: pd.DataFrame | None) -> str:
    if panel is None or not len(panel):
        return ""
    p = panel.copy()
    p["cobertura_pct"] = 100 * p.en_panel_desarrollo / p.total_personas
    bd = p[p.perfil.isin(["bajo_desempeno", "nuevo_dificil"])]
    txt = """
### Alcance del panel `desarrollo`

La mitad "baja productividad" del mandato del caso, cerrada en v1.1.0. No es
una métrica de predicción de salida —este canal no existe para eso—: mide, de
cada perfil latente, qué fracción de TODA su población (no solo quien salió)
aparece alguna vez en el panel mientras sigue en Buk.

"""
    txt += _md(p, 1)
    if len(bd):
        txt += f"""

En v1.0.0 `bajo_desempeno` y `nuevo_dificil` estaban en **0.0%** de cobertura
en todo canal — la señal que los alcanzaba (`desempeno_bajo`) había sido
descartada del catálogo completo, no solo del canal de retención. R06 los
alcanza en **{bd[bd.perfil=='bajo_desempeno'].cobertura_pct.iloc[0]:.1f}%** y
**{bd[bd.perfil=='nuevo_dificil'].cobertura_pct.iloc[0]:.1f}%** respectivamente,
con baja fuga hacia perfiles que no debería tocar (`estable` en
{p[p.perfil=='estable'].cobertura_pct.iloc[0]:.1f}%).
"""
    return txt


def resultados(cat: dict, m: dict, techo: pd.DataFrame | None, corte: str, ult: str,
                panel_dev: pd.DataFrame | None = None) -> str:
    txt = f"""
## Qué produce este catálogo

> **Advertencia que va antes de los números.** Estos resultados vienen de datos
> sintéticos con estructura causal conocida: el generador puso ahí las
> relaciones que el backtest encuentra. Esto valida el *método* —que la tubería
> corre, que las métricas se calculan sobre la población correcta, que la
> censura está bien tratada—. No es evidencia de que el sistema funcione en
> Buk. Eso solo lo dice una corrida sobre datos reales.

Ventana de acierto: **{VENTANA_MESES} meses**. Se evalúa hasta **{corte}** aunque el
dato llegue a **{ult}**: nadie puede salir en {VENTANA_MESES} meses si solo quedan
{VENTANA_MESES} meses de historia (censura a la derecha).

| Métrica | Valor | Lectura |
|---|---|---|
| Carga | **{m['alertas_mes']:.1f} alertas/mes** | contra un cupo de {cat['operacion']['canales']['conversacion']['cupo_mensual']} |
| Precisión (salida lamentada) | **{100*m['precision_lamentada']:.1f}%** | base {100*m['base_lamentada']:.1f}% · **lift {m['lift_lamentada']:.2f}x** |
| Precisión (cualquier salida) | {100*m['precision_cualquiera']:.1f}% | base {100*m['base_cualquiera']:.1f}% · lift {m['lift_cualquiera']:.2f}x |
| Cobertura | **{m['cubiertas']} de {m['salidas_lamentadas']} = {100*m['cobertura']:.1f}%** | salidas lamentadas alcanzadas antes |
| Costo sobre quien se queda | {m['quedan_alertados']:,} de {m['quedan']:,} = **{100*m['carga_falsa']:.1f}%** | apareció en una alerta y sigue en Buk |

La última fila es la que casi nunca se muestra y la que más importa: cada
persona ahí es alguien que no se iba y aun así llegó a una lista. Es el precio
del sistema, y se publica junto al beneficio.
"""
    if techo is not None:
        t = techo.copy()
        t["cobertura_pct"] = 100 * t.cubiertas / t.salidas_lamentadas
        estable = t[t.perfil == "estable"]
        txt += "\n### Techo de cobertura\n\n"
        txt += _md(t, 1)
        if len(estable):
            pct = 100 * estable.salidas_lamentadas.iloc[0] / t.salidas_lamentadas.sum()
            txt += f"""

El **{pct:.0f}%** de las salidas lamentadas viene del perfil `estable`: gente sin
deterioro previo por construcción —una oferta inesperada, una mudanza, un cambio
de vida—. Ninguna regla, y ningún modelo, la ve venir. **La cobertura máxima
alcanzable es ~{100-pct:.0f}%**, y decirlo por adelantado es parte del diseño: un
sistema que prometiera detectar el 100% describiría un mundo donde las personas
son predecibles.
"""
    txt += panel_desarrollo(panel_dev)
    return txt


def calibracion(cat: dict, curva: pd.DataFrame) -> str:
    cupo = cat["operacion"]["canales"]["conversacion"]["cupo_mensual"]
    enf = cat["operacion"]["canales"]["conversacion"]["enfriamiento_meses"]
    tabla = curva[curva.enfriamiento == enf]

    # El argumento del enfriamiento se recalcula en cada corrida: si una versión
    # futura mueve estas tres cifras, el texto se mueve con ellas.
    sin_tope = curva[curva.cupo == 9999].set_index("enfriamiento")
    e0, e3 = sin_tope.loc[0], sin_tope.loc[enf]
    caida_volumen = round((1 - e3.alertas_mes / e0.alertas_mes) * 100)
    costo_cobertura = _coma(e0.cobertura - e3.cobertura, 1)
    cargas = sin_tope.carga_falsa.round(2).unique()
    carga_estable = (f"no cambia en absoluto ({_coma(cargas[0])}% en los tres casos)"
                     if len(cargas) == 1 else
                     "se mueve poco (" + " · ".join(f"{_coma(c)}%" for c in cargas) + ")")
    return f"""
## Curva de calibración

La respuesta honesta a *"¿por qué {cupo} y no 100?"*. No es que {cupo} maximice algo:
es lo que People Happiness puede atender de verdad. La tabla muestra exactamente
cuánta cobertura cuesta esa restricción, con enfriamiento de {enf} meses.

{_tabla(tabla, {'cupo': 'Cupo', 'alertas_mes': 'Alertas/mes',
                'precision_lamentada': 'Precisión %', 'lift': 'Lift',
                'cobertura': 'Cobertura %', 'carga_falsa': 'Carga falsa %'})}

Lo que dice la curva: la cobertura **satura**. Multiplicar el cupo por cuatro no
multiplica la cobertura — agrega alertas cada vez peores sobre gente que se
queda. El cupo no es el cuello de botella; el poder de las señales sí.

### El enfriamiento es la palanca, no el cupo

El efecto del enfriamiento hay que medirlo **sin tope**, porque con tope el cupo
lo esconde: al recortar repeticiones, el enfriamiento simplemente deja entrar a
otra persona y el volumen no se mueve.

{_tabla(curva[curva.cupo == 9999], {'enfriamiento': 'Enfriamiento (meses)',
                                    'alertas_mes': 'Alertas/mes',
                                    'precision_lamentada': 'Precisión %',
                                    'cobertura': 'Cobertura %',
                                    'carga_falsa': 'Carga falsa %'})}

Ahí se ve el argumento entero del bloque: pasar de 0 a {enf} meses de enfriamiento
elimina el **{caida_volumen}% del volumen** y cuesta **{costo_cobertura} puntos de
cobertura**. La fracción de gente que se queda y aparece alertada {carga_estable}:
son exactamente las mismas personas, avisadas menos veces.

Ese es el hallazgo que ordenó la calibración. El problema nunca fue que los
umbrales estuvieran bajos —subirlos habría costado cobertura real—: era que el
sistema le repetía a la misma persona la misma alerta todos los meses. Se
arregló dejando de repetir, no dejando de mirar.
"""


def auditoria(paneles: dict[str, pd.DataFrame]) -> str:
    cols = {"grupo": "Grupo", "personas": "Personas", "meses_expuesto": "Meses expuesto",
            "alertas_1000m": "Alertas/1.000 meses", "tasa_salida": "Tasa salida lam.",
            "salidas_lamentadas": "Salidas lam.", "cobertura": "Cobertura",
            "indice_alerta": "Índice alerta", "indice_cobertura": "Índice cobertura",
            "estado": "Estado"}
    partes = [f"""
## Auditoría de impacto dispar

Se prohíbe usar un atributo protegido como condición **y** se obliga a medir
sobre quién cae el sistema. Lo primero sin lo segundo es una garantía de papel:
un modelo puede discriminar sin nombrar nunca al grupo que discrimina, porque
las variables que sí usa están correlacionadas con él.

Se miden tres cosas, y la distinción importa más que los números:

- **Paridad demográfica** — ¿alertamos parejo? Es la métrica intuitiva y es
  insuficiente sola: si un grupo tiene más riesgo real, alertarlo más es hacer
  el trabajo.
- **Igualdad de oportunidad** — de quienes salieron doliendo, ¿a qué fracción
  llegamos en cada grupo? Esta es la métrica ética: mide el reparto del
  beneficio, no el del castigo.
- **Exposición** — nadie puede ser alertado un mes en que no era elegible. La
  tasa se calcula por mes-persona expuesto; medirla por cabeza compara gente que
  corrió distancias distintas.

Se marca un grupo cuando el índice sale de [{equidad.PISO:.2f}, {equidad.TECHO:.2f}]
(regla del 80%, EEOC) **y además** la diferencia supera lo que el azar binomial
explica (dos proporciones, |z| > {equidad.Z_MINIMO:.0f}). Las dos condiciones
juntas, no una: marcar de más entrena al comité a ignorar la lista. Grupos bajo
{equidad.N_MINIMO} personas se agregan; el índice de cobertura solo se publica con
al menos {equidad.SALIDAS_MINIMAS} salidas lamentadas.
"""]
    for titulo, atributos in [("Atributos protegidos", equidad.PROTEGIDOS),
                              ("Ejes de gobernanza (no protegidos)", equidad.GOBERNANZA)]:
        partes.append(f"\n### {titulo}\n")
        for a in atributos:
            partes.append(f"**`{a}`**\n")
            partes.append(_tabla(paneles[a], cols, 3) + "\n")
    return "\n".join(partes)


def _coma(x: float, decimales: int = 2) -> str:
    return f"{x:.{decimales}f}".replace(".", ",")


# Análisis registrado para cada desviación conocida, indexado por (atributo, grupo).
# Las cifras que cita el texto se inyectan desde el panel, no se transcriben: así una
# desviación no puede quedar descrita con el número de una corrida anterior. Un grupo
# marcado sin nota acá aparece listado como pendiente — lo que no se puede es que
# quede marcado y sin explicar en silencio.
NOTAS_DESVIACION: dict[tuple[str, str], str] = {
    ("pais_contrato", "BR"): """
- **`pais_contrato` = BR** (índice de alerta {ia}). Paso 1 lo resuelve: Brasil
  tiene la mayor tasa de salida lamentada ({ts}) y el `compa_ratio` medio más
  bajo (0,965), con 3,7% de dotación bajo banda contra 1,2% en Chile. El sistema
  no está sesgado contra Brasil: está encontrando un problema de estructura
  salarial en Brasil. El hallazgo es para Compensaciones, no para el catálogo.""",
    ("job_family", "Marketing"): """
- **`job_family` = Marketing** (índice de alerta {ia}). Paso 2. Marketing no
  tiene CSAT —no es cara al cliente— y su métrica de productividad es la menos
  dispersa de la compañía (sd 2,41 contra 2,7 típico) y la que menos deriva a la
  baja (−0,10 contra −0,37). Tres de las cinco reglas le son inalcanzables en la
  práctica, y el umbral absoluto de caída (−3,0 puntos) casi no se activa en una
  métrica que no se mueve. **Está sub-detectada por instrumentación, no por
  sesgo.** Corregirlo pide normalizar la caída de productividad dentro de la
  familia, y eso es un cambio de catálogo con backtest propio, no un parche.""",
    ("tramo_antiguedad", "12-23"): """
- **`tramo_antiguedad`** (cobertura de 12-23 y 24-47 sobre 0-11, índices {ic} y
  2,65). Ver la limitación declarada más abajo: es exposición, y es el hallazgo
  más importante de esta corrida.""",
    ("tramo_antiguedad", "24-47"): "",  # cubierto en la nota de 12-23
    ("tramo_antiguedad", "48+"): """
- **`tramo_antiguedad` = 48+** (índice de alerta {ia}). Paso 1 lo resuelve en el
  sentido contrario al de Brasil: quienes llevan cuatro años o más tienen la
  **menor** tasa de salida lamentada de la compañía ({ts} contra 0,194 del tramo
  0-11). Se les alerta menos porque se van menos.""",
    ("nacionalidad", "Mexicana"): """
- **`nacionalidad` = Mexicana** (índice de alerta {ia}, índice de cobertura
  {ic}). Atributo protegido, así que el estándar de prueba es más alto. El
  desvío de cobertura es a favor y es grande: de quienes salieron doliendo se
  alcanza a casi tres veces la fracción del grupo de referencia. El de alerta
  queda abierto: con tasa de salida {ts} —por debajo de la referencia (0,121)—
  el paso 1 no lo explica. Se registra, se revisa el próximo trimestre y con
  {sl} salidas lamentadas todavía puede ser ruido que el test no descarta.""",
    ("nacionalidad", "Peruana"): """
- **`nacionalidad` = Peruana** (índice de alerta {ia}, índice de cobertura
  {ic}). **Este es el hallazgo abierto de la corrida y el que impide publicar
  esta versión sin revisión.** Ninguno de los tres pasos lo cierra. El paso 1 lo
  contradice: la tasa de salida lamentada del grupo es {ts}, la más baja entre
  los grupos grandes y por debajo de la referencia chilena (0,121) — se alerta
  {exceso}% más a un grupo que se va menos. El paso 2 explica de dónde salen las
  alertas pero no las justifica: las métricas de origen sí se deterioran más
  (caída de productividad a 3 meses −0,394 contra −0,276 en el grupo de
  referencia, caída de CSAT −0,020 contra −0,010), y la mezcla de familias de
  cargo no lo produce —Perú pesa más en Soporte, que es la familia con **menos**
  alertas por exposición—. Queda una señal que se mueve sin que el resultado la
  siga. Hasta entenderlo, la versión no se despliega sola: es exactamente el
  caso que el veto de auditoría existe para detener.""",
}


def hallazgos(paneles: dict[str, pd.DataFrame]) -> str:
    filas = [(a, f) for a, df in paneles.items()
             for _, f in df.iterrows() if str(f.estado).startswith("REVISAR")]
    lista = "\n".join(f"- `{a}` = **{f.grupo}** — {f.estado}" for a, f in filas)

    notas, pendientes = [], []
    for atributo, f in filas:
        plantilla = NOTAS_DESVIACION.get((atributo, f.grupo))
        if plantilla is None:
            pendientes.append(f"- `{atributo}` = **{f.grupo}** — desviación nueva en "
                              f"esta corrida, sin análisis registrado. Bloquea la "
                              f"publicación hasta que se documente.")
            continue
        if not plantilla:
            continue
        exceso = round((f.indice_alerta - 1) * 100)
        notas.append(plantilla.format(
            ia=_coma(f.indice_alerta), ic=_coma(f.indice_cobertura),
            ts=_coma(f.tasa_salida, 3), sl=int(f.salidas_lamentadas), exceso=exceso))

    # La frase de cierre se calcula: si una versión futura marca un grupo protegido
    # por índice de alerta, este párrafo lo dice solo.
    protegidos = [(a, f) for a, f in filas
                  if a in equidad.PROTEGIDOS and "alerta" in str(f.estado)]
    if protegidos:
        cuales = ", ".join(f"`{a}` = {f.grupo}" for a, f in protegidos)
        cierre = (f"**{len(protegidos)} grupo(s) de atributo protegido quedaron marcados "
                  f"por índice de alerta** ({cuales}). No es prueba de que el sistema "
                  f"discrimine —el índice mide alertas, no daño— pero sí es la condición "
                  f"que obliga a revisar antes de publicar, y no se levanta sola.")
    else:
        cierre = ("Ningún grupo protegido quedó marcado por índice de alerta. Eso no "
                  "prueba que el sistema sea justo: prueba que en estos datos, con estos "
                  "grupos y este umbral, no se detectó impacto dispar.")

    bloque_pendientes = ("\n\n**Sin análisis registrado:**\n\n" + "\n".join(pendientes)
                         if pendientes else "")

    return f"""
### Hallazgos de esta corrida

{len(filas)} grupo(s) fuera de banda. No es un veredicto: es la lista de lo que
hay que mirar antes de publicar esta versión.

{lista}

**Cómo se lee una desviación, en orden.** El protocolo importa más que
cualquier hallazgo puntual, porque es lo que impide dos errores opuestos:
corregir un sesgo que no existe, y tapar uno que sí.

1. **¿La tasa de salida real del grupo también es distinta?** Entonces el
   sistema está siguiendo el riesgo, no creándolo.
2. **¿Hay una señal cuya métrica de origen se comporta distinto en ese grupo?**
   El problema está en la métrica, no en la gente.
3. **Recién entonces: revisar umbrales.** Nunca añadir el atributo como
   condición.

Aplicado a lo marcado arriba:
{"".join(notas)}{bloque_pendientes}

{cierre}
"""


def aporte_del_panel(con: duckdb.DuckDBPyConnection) -> tuple[int, int, float]:
    """Cuántas salidas lamentadas de la cohorte 0-11 recupera el panel de
    compensaciones, que sí alcanza a un recién llegado. Se mide en puntos de
    cobertura: los dos porcentajes tienen denominadores distintos y compararlos
    de frente sería trampa."""
    fila = con.execute(f"""
        WITH nuevos AS (
          SELECT s.employee_id, s.idx_salida
          FROM salidas s
          JOIN employee_360 e ON e.employee_id = s.employee_id
                             AND e.idx_mes = s.idx_salida - 1
          WHERE s.lamentada AND e.tramo_antiguedad = '0-11'
        )
        SELECT COUNT(DISTINCT n.employee_id) AS salidas,
               COUNT(DISTINCT CASE WHEN c.employee_id IS NOT NULL
                                   THEN n.employee_id END) AS solo_alerta,
               COUNT(DISTINCT CASE WHEN c.employee_id IS NOT NULL
                                     OR p.employee_id IS NOT NULL
                                   THEN n.employee_id END) AS con_panel
        FROM nuevos n
        LEFT JOIN (SELECT DISTINCT employee_id, idx_mes FROM alertas_bt
                   WHERE estado = 'notificada') c
               ON c.employee_id = n.employee_id
              AND c.idx_mes BETWEEN n.idx_salida - {VENTANA_MESES} AND n.idx_salida - 1
        LEFT JOIN (SELECT DISTINCT employee_id, idx_mes FROM alertas_bt
                   WHERE canal = 'compensaciones') p
               ON p.employee_id = n.employee_id
              AND p.idx_mes BETWEEN n.idx_salida - {VENTANA_MESES} AND n.idx_salida - 1
    """).fetchone()
    salidas, solo, con_panel = fila
    puntos = 100 * (con_panel - solo) / salidas if salidas else 0.0
    return con_panel - solo, salidas, puntos


def limitaciones(paneles: dict[str, pd.DataFrame],
                 aporte: tuple[int, int, float]) -> str:
    """Las limitaciones se declaran con las cifras de ESTA corrida, no con las de
    la versión en que se escribieron. El hallazgo de antigüedad es el argumento
    más fuerte del documento; que se quede con un número viejo lo desarma."""
    ant = paneles["tramo_antiguedad"].set_index("grupo")
    nuevos, siguiente = ant.loc["0-11"], ant.loc["12-23"]
    total_lamentadas = ant.salidas_lamentadas.sum()
    cob_nuevos = 100 * nuevos.cobertura
    concentra = round(100 * nuevos.salidas_lamentadas / total_lamentadas)
    # Por cabeza el sesgo parece brutal; por exposición desaparece. Las dos
    # lecturas de la misma cohorte son el punto entero de esta sección.
    por_cabeza = ((siguiente.alertas_1000m * siguiente.meses_expuesto)
                  / (nuevos.alertas_1000m * nuevos.meses_expuesto))
    recuperadas, salidas_cohorte, puntos_panel = aporte

    return f"""
## Limitaciones declaradas

Se declaran acá para que se discutan, no para que se descubran.

### 1. El sistema casi no ve a quien recién llegó — y es quien más se va

El hallazgo más incómodo de la auditoría. La cohorte de 0-11 meses tiene la
**mayor** tasa de salida lamentada ({_coma(nuevos.tasa_salida, 3)} contra
{_coma(siguiente.tasa_salida, 3)} del siguiente tramo) y concentra el **{concentra}% de todas
las salidas lamentadas**. Su cobertura es {_coma(cob_nuevos, 1)}%.

Medido por cabeza parecía un sesgo brutal: {_coma(por_cabeza, 1)}x menos alertas que el
tramo siguiente. Medido por mes-persona expuesto se da vuelta: {_coma(nuevos.alertas_1000m, 1)} alertas
por cada mil meses contra {_coma(siguiente.alertas_1000m, 1)} del tramo 12-23 — a quien está en el
universo se le alerta prácticamente al mismo ritmo que a todos. La diferencia
entera es tiempo: un recién llegado está en el universo **{_coma(nuevos.meses_expuesto, 1)} meses** en
promedio, contra **{_coma(siguiente.meses_expuesto, 1)}** del tramo siguiente.

No es un defecto de las reglas: es que las reglas necesitan historia. Las
ventanas móviles piden 3 meses, la caída de evaluación pide dos evaluaciones, y
el universo empieza a los 3 meses de antigüedad. Cuando el sistema puede
observar a alguien, esa persona ya se fue.

**Por qué no se arregla con el panel de compensaciones.** Las reglas de
compensación sí alcanzan a un recién llegado: `compa_ratio` existe desde el día
uno y la evaluación de los 3 meses le da un nivel de desempeño. Se midió: sumar
el panel recupera **{recuperadas} de las {salidas_cohorte} salidas lamentadas** de la
cohorte —**{_coma(puntos_panel, 1)} puntos de cobertura**—. Ayuda, no resuelve.

**Qué le falta exactamente.** No le falta *una* señal: le falta la *segunda*
evaluación. Con contrato a plazo fijo y evaluación formal a los 3 meses, un
recién llegado tiene nivel de desempeño pero no tiene delta, y las tres reglas
del canal de conversación se apoyan en deltas. El sistema lo ve quieto y no lo
ve moverse.

**Consecuencia:** este catálogo no es un instrumento de onboarding y no debe
venderse como tal. El riesgo temprano necesita un instrumento propio que no
dependa de comparar contra el pasado. El más barato está a la mano: la
evaluación de 3 meses ya mide **tres ejes separados** —valores, competencias y
métricas del cargo—. Si se leen por separado en vez de agregados en un score,
son tres dimensiones de evidencia disponibles en el mes 3, suficientes para
fundar una regla de onboarding sin ninguna serie de tiempo. Es la primera línea
del roadmap, y es una línea concreta.

### 2. Los datos son sintéticos

El generador puso las relaciones causales que el backtest encuentra. Lo validado
es el método, no el resultado. Los umbrales de este catálogo son puntos de
partida razonados, no valores calibrados sobre Buk.

### 3. La cobertura tiene techo y no es alto

Cerca del 41% de las salidas lamentadas no tiene ninguna señal previa por
construcción. Con datos reales el techo será otro, pero existirá igual.

### 4. Una alerta correcta no es una retención

Todo lo que este documento mide termina en "se abrió una conversación a tiempo".
Si esa conversación sirve depende de qué pase en ella, y eso no lo mide ninguna
tabla de este documento.

### 5. El panel `desarrollo` (v1.1.0) todavía no pasó por la auditoría de equidad

`equidad.py` audita hoy el canal `conversacion` porque ahí nació el catálogo.
El panel `desarrollo`, agregado en v1.1.0 para cerrar la mitad "baja
productividad" del mandato, usa dos señales de NIVEL (no de tendencia) —
`score_vigente` y `prod_prom_3m` absolutos— que son precisamente el tipo de
métrica más expuesta a diferencias de instrumentación entre `job_family` (ver
el hallazgo de Marketing en la sección anterior, sobre una señal de tendencia).
No auditar esto antes de publicar sería repetir, en el canal nuevo, el mismo
error que esta versión corrigió en el canal viejo: declarar una garantía sin
medirla. Queda como el primer punto del roadmap, no como un supuesto.
"""


def bitacora(cat: dict) -> str:
    partes = ["""
## Bitácora de versiones

Buk registró 325 cambios internos en un año y los deja escritos. Un catálogo que
decide sobre personas se sostiene con la misma disciplina: cada cambio de umbral
queda con fecha, autor y motivo, y el backtest y la auditoría se archivan con la
versión. Sin esto, "revisamos trimestralmente" es una intención.
"""]
    for b in cat["bitacora"]:
        partes.append(f"**v{b['version']} · {b['fecha']} · {b['autor']}**  \n"
                      f"{_parrafo(b['cambio'])}\n")
    return "\n".join(partes)


# ---------------------------------------------------------------------------

def main() -> None:
    cat = cargar()
    con = duckdb.connect(str(BD), read_only=True)
    _preparar(con, cat)

    m = metricas(con)
    ult = con.execute("SELECT MAX(periodo) FROM employee_360").fetchone()[0]
    corte = con.execute("SELECT MAX(periodo) FROM employee_360 "
                        f"WHERE idx_mes <= {m['corte_censura']}").fetchone()[0]
    techo = techo_de_cobertura(con)
    panel_dev = cobertura_panel_desarrollo(con)
    lift = lift_por_senal(con, cat)
    curva = curva_de_calibracion(con, cat)
    paneles = {a: equidad.auditar(con, a) for a in equidad.PROTEGIDOS + equidad.GOBERNANZA}

    partes = [
        encabezado(cat),
        garantias(cat),
        senales(cat, lift),
        descartes(cat),
        reglas(cat),
        operacion(cat),
        resultados(cat, m, techo, corte, ult, panel_dev),
        calibracion(cat, curva),
        auditoria(paneles),
        hallazgos(paneles),
        limitaciones(paneles, aporte_del_panel(con)),
        bitacora(cat),
    ]
    DESTINO.write_text("\n".join(partes), encoding="utf-8")
    con.close()
    print(f"Escrito: {DESTINO.name} "
          f"({len(DESTINO.read_text(encoding='utf-8').splitlines()):,} líneas)")


if __name__ == "__main__":
    main()
