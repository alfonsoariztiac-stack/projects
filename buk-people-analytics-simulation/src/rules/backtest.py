"""
Backtest: qué habría pasado si el sistema hubiera estado encendido.

Lo primero que hay que decir en voz alta, antes que cualquier número:

    Los datos son sintéticos y se generaron con una estructura causal latente.
    El backtest funciona en parte POR CONSTRUCCIÓN. Lo que estas métricas
    demuestran es que el método de validación existe y está bien montado —
    corrección temporal, censura a la derecha, techo declarado—, no que el
    sistema vaya a funcionar sobre datos reales de Buk. Sobre datos reales
    este mismo archivo correría igual y daría otros números.

Lo segundo: el objetivo NO es "predecir salidas". Es predecir SALIDAS
LAMENTADAS —quien cumplía o superaba lo esperado y renunció—. Medir contra
"salida a secas" premia a un sistema que señala bajo desempeño, que es
exactamente el sesgo que el diseño debe evitar. Las dos métricas se calculan y
se muestran juntas para que la diferencia quede a la vista.

Tres decisiones metodológicas que sostienen los números:

- **Censura a la derecha.** Nadie puede "salir en los próximos 6 meses" si el
  dato se corta en 6 meses. Los últimos periodos se excluyen del cálculo de
  precisión en vez de contarse como aciertos fallidos.
- **Precisión por alerta, cobertura por persona.** Son preguntas distintas:
  cuánta de la carga del HM es útil, y a cuánta gente que se fue alcanzamos.
- **El techo se declara antes de mostrar el resultado.** Una fracción de las
  salidas no tiene señal previa por construcción (oferta inesperada, mudanza).
  Un backtest que las detectara estaría describiendo un mundo donde las
  personas son predecibles.
"""

from __future__ import annotations

import pathlib
import sys

import duckdb
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from motor import cargar, compilar  # noqa: E402
from warehouse import BD  # noqa: E402

VENTANA_MESES = 6          # cuánto tiempo hacia adelante cuenta como "acierto"
LABORATORIO = pathlib.Path(__file__).parent.parent.parent / "data" / "laboratorio"


# ---------------------------------------------------------------------------
# Preparación
# ---------------------------------------------------------------------------

def _preparar(con: duckdb.DuckDBPyConnection, cat: dict) -> None:
    """Deja en la sesión las tablas del backtest.

    `salidas` sale de employee_360 usando columnas que el motor tiene prohibido
    leer. Esa asimetría es el punto: las etiquetas existen para evaluar, y viven
    fuera del camino que produce alertas.
    """
    con.execute("""
        CREATE OR REPLACE TEMP TABLE salidas AS
        SELECT employee_id,
               MIN(idx_mes) AS idx_salida,
               MAX(CASE WHEN salida_lamentada THEN 1 ELSE 0 END) = 1 AS lamentada
        FROM employee_360
        WHERE fecha_salida IS NOT NULL AND NOT activo_en_el_mes
        GROUP BY employee_id
    """)
    con.execute(f"CREATE OR REPLACE TEMP TABLE alertas_bt AS {compilar(cat)}")
    con.execute("""
        CREATE OR REPLACE TEMP TABLE universo_bt AS
        SELECT e.employee_id, e.idx_mes, e.periodo,
               CASE WHEN s.idx_salida BETWEEN e.idx_mes + 1 AND e.idx_mes + %d
                    THEN TRUE ELSE FALSE END AS sale,
               CASE WHEN s.lamentada AND s.idx_salida BETWEEN e.idx_mes + 1 AND e.idx_mes + %d
                    THEN TRUE ELSE FALSE END AS sale_lamentada
        FROM employee_360 e
        LEFT JOIN salidas s ON s.employee_id = e.employee_id
        WHERE %s
    """ % (VENTANA_MESES, VENTANA_MESES, cat["universo"]["condicion"]))


def _corte_censura(con: duckdb.DuckDBPyConnection) -> int:
    """Último mes con ventana completa de observación hacia adelante."""
    return con.execute("SELECT MAX(idx_mes) - %d FROM employee_360" % VENTANA_MESES).fetchone()[0]


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------

def metricas(con: duckdb.DuckDBPyConnection, canal: str = "conversacion") -> dict:
    corte = _corte_censura(con)
    base = con.execute(
        "SELECT AVG(CASE WHEN sale_lamentada THEN 1.0 ELSE 0 END), "
        "       AVG(CASE WHEN sale THEN 1.0 ELSE 0 END) "
        f"FROM universo_bt WHERE idx_mes <= {corte}").fetchone()

    vol = con.execute(f"""
        SELECT COUNT(*) * 1.0 / COUNT(DISTINCT periodo)
        FROM alertas_bt WHERE canal = '{canal}' AND estado = 'notificada'""").fetchone()[0]

    prec = con.execute(f"""
        SELECT AVG(CASE WHEN u.sale_lamentada THEN 1.0 ELSE 0 END),
               AVG(CASE WHEN u.sale THEN 1.0 ELSE 0 END),
               COUNT(*)
        FROM alertas_bt a
        JOIN universo_bt u ON u.employee_id = a.employee_id AND u.idx_mes = a.idx_mes
        WHERE a.canal = '{canal}' AND a.estado = 'notificada' AND a.idx_mes <= {corte}""").fetchone()

    # Cobertura: de quienes se fueron, a cuántos tocamos con al menos una alerta
    # en los N meses previos. Se cuenta la persona, no la alerta.
    cob = con.execute(f"""
        SELECT COUNT(DISTINCT s.employee_id),
               COUNT(DISTINCT CASE WHEN a.employee_id IS NOT NULL THEN s.employee_id END)
        FROM salidas s
        LEFT JOIN alertas_bt a
               ON a.employee_id = s.employee_id
              AND a.estado = 'notificada'
              AND a.idx_mes BETWEEN s.idx_salida - {VENTANA_MESES} AND s.idx_salida - 1
        WHERE s.lamentada""").fetchone()

    # Carga sobre quien se queda: la métrica ética. Cada persona aquí es alguien
    # que no se fue y aun así apareció en una lista.
    quedan = con.execute("""
        SELECT COUNT(DISTINCT e.employee_id)
        FROM employee_360 e
        WHERE e.employee_id NOT IN (SELECT employee_id FROM salidas)""").fetchone()[0]
    quedan_alertados = con.execute(f"""
        SELECT COUNT(DISTINCT a.employee_id) FROM alertas_bt a
        WHERE a.canal = '{canal}' AND a.estado = 'notificada'
          AND a.employee_id NOT IN (SELECT employee_id FROM salidas)""").fetchone()[0]

    return {
        "canal": canal,
        "corte_censura": corte,
        "base_lamentada": base[0],
        "base_cualquiera": base[1],
        "alertas_mes": vol,
        "alertas_evaluadas": prec[2],
        "precision_lamentada": prec[0],
        "precision_cualquiera": prec[1],
        "lift_lamentada": prec[0] / base[0],
        "lift_cualquiera": prec[1] / base[1],
        "salidas_lamentadas": cob[0],
        "cubiertas": cob[1],
        "cobertura": cob[1] / cob[0],
        "quedan": quedan,
        "quedan_alertados": quedan_alertados,
        "carga_falsa": quedan_alertados / quedan,
    }


def techo_de_cobertura(con: duckdb.DuckDBPyConnection) -> pd.DataFrame | None:
    """Cuánta de la rotación es detectable en principio, según el perfil latente.

    Solo existe porque los datos son sintéticos y sabemos quién es quién. Es la
    pieza que impide vender el resultado como mejor de lo que es: el perfil
    `estable` se va sin señal previa por construcción, y ninguna regla —ni un
    modelo— lo vería venir.
    """
    ruta = LABORATORIO / "_verdad_latente.csv"
    if not ruta.exists():
        return None
    con.execute(f"CREATE OR REPLACE TEMP TABLE latente AS SELECT * FROM read_csv_auto('{ruta}')")
    return con.execute(f"""
        SELECT l.perfil_latente AS perfil,
               COUNT(DISTINCT s.employee_id) AS salidas_lamentadas,
               COUNT(DISTINCT CASE WHEN a.employee_id IS NOT NULL THEN s.employee_id END) AS cubiertas
        FROM salidas s
        JOIN latente l ON l.employee_id = s.employee_id
        LEFT JOIN alertas_bt a
               ON a.employee_id = s.employee_id AND a.estado = 'notificada'
              AND a.idx_mes BETWEEN s.idx_salida - {VENTANA_MESES} AND s.idx_salida - 1
        WHERE s.lamentada
        GROUP BY 1 ORDER BY 2 DESC""").df()


def cobertura_panel_desarrollo(con: duckdb.DuckDBPyConnection) -> pd.DataFrame | None:
    """Cuánta de la mitad "baja productividad" del mandato alcanza el panel `desarrollo`.

    No es una métrica de predicción de salida —el canal `desarrollo` no existe
    para eso—, es una métrica de alcance: de cada perfil latente, qué fracción
    aparece alguna vez en el panel. A diferencia de `techo_de_cobertura`, aquí
    se mide sobre TODA la población del perfil, no solo sobre quienes salieron:
    el objetivo de este canal es llegar a la persona mientras sigue en Buk, no
    antes de que se vaya.
    """
    ruta = LABORATORIO / "_verdad_latente.csv"
    if not ruta.exists():
        return None
    con.execute(f"CREATE OR REPLACE TEMP TABLE latente AS SELECT * FROM read_csv_auto('{ruta}')")
    return con.execute("""
        SELECT l.perfil_latente AS perfil,
               COUNT(DISTINCT l.employee_id) AS total_personas,
               COUNT(DISTINCT CASE WHEN a.employee_id IS NOT NULL
                     THEN l.employee_id END) AS en_panel_desarrollo
        FROM latente l
        LEFT JOIN alertas_bt a
               ON a.employee_id = l.employee_id
              AND a.canal = 'desarrollo' AND a.estado = 'en_panel'
        GROUP BY 1 ORDER BY 3 DESC""").df()


def lift_por_senal(con: duckdb.DuckDBPyConnection, cat: dict) -> pd.DataFrame:
    """Recalcula el poder de cada señal por separado. Alimenta el catálogo.

    Si el `lift_medido` que declara reglas.yaml y el que sale de aquí divergen,
    manda este: el YAML documenta, el backtest mide.
    """
    from motor import expresion
    corte = _corte_censura(con)
    filas = []
    for sid, s in cat["senales"].items():
        expr = expresion(cat, sid)
        r = con.execute(f"""
            SELECT AVG(CASE WHEN ({expr}) THEN 1.0 ELSE 0 END) AS disparo,
                   AVG(CASE WHEN ({expr}) AND u.sale_lamentada THEN 1.0 ELSE 0 END)
                     / NULLIF(AVG(CASE WHEN ({expr}) THEN 1.0 ELSE 0 END), 0) AS prec_lam,
                   AVG(CASE WHEN ({expr}) AND u.sale THEN 1.0 ELSE 0 END)
                     / NULLIF(AVG(CASE WHEN ({expr}) THEN 1.0 ELSE 0 END), 0) AS prec_any,
                   AVG(CASE WHEN u.sale_lamentada THEN 1.0 ELSE 0 END) AS base_lam,
                   AVG(CASE WHEN u.sale THEN 1.0 ELSE 0 END) AS base_any
            FROM employee_360 e
            JOIN universo_bt u ON u.employee_id = e.employee_id AND u.idx_mes = e.idx_mes
            WHERE e.idx_mes <= {corte}""").df().iloc[0]
        filas.append({
            "senal": sid, "dimension": s["dimension"], "tipo": s["tipo"],
            "dispara_pct": 100 * r.disparo,
            "lift_lamentada": r.prec_lam / r.base_lam,
            "lift_cualquiera": r.prec_any / r.base_any,
            "declarado": s.get("lift_medido"),
        })
    return pd.DataFrame(filas).sort_values("lift_lamentada", ascending=False)


def curva_de_calibracion(con: duckdb.DuckDBPyConnection, cat: dict) -> pd.DataFrame:
    """El menú de puntos de operación: qué cobertura compra cada nivel de carga.

    Esta tabla es la respuesta honesta a "¿por qué 35 y no 100?". La respuesta
    no es que 35 maximice nada: es que 35 es lo que el equipo puede atender, y
    la tabla muestra exactamente cuánta cobertura cuesta esa restricción.
    """
    import copy
    filas = []
    for cupo in [15, 25, 35, 50, 75, 100, 150, 9999]:
        for enfriamiento in [0, 3, 6]:
            variante = copy.deepcopy(cat)
            variante["operacion"]["canales"]["conversacion"]["cupo_mensual"] = cupo
            variante["operacion"]["canales"]["conversacion"]["enfriamiento_meses"] = enfriamiento
            con.execute(f"CREATE OR REPLACE TEMP TABLE alertas_bt AS {compilar(variante)}")
            m = metricas(con)
            filas.append({
                "cupo": cupo, "enfriamiento": enfriamiento,
                "alertas_mes": m["alertas_mes"],
                "precision_lamentada": 100 * m["precision_lamentada"],
                "lift": m["lift_lamentada"],
                "cobertura": 100 * m["cobertura"],
                "carga_falsa": 100 * m["carga_falsa"],
            })
    con.execute(f"CREATE OR REPLACE TEMP TABLE alertas_bt AS {compilar(cat)}")
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------

def main() -> dict:
    cat = cargar()
    con = duckdb.connect(str(BD), read_only=True)
    _preparar(con, cat)

    m = metricas(con)
    ult = con.execute("SELECT MAX(periodo) FROM employee_360").fetchone()[0]
    corte_periodo = con.execute(
        f"SELECT MAX(periodo) FROM employee_360 WHERE idx_mes <= {m['corte_censura']}").fetchone()[0]

    print("=" * 74)
    print(f"BACKTEST · catálogo v{cat['version']} · canal conversación")
    print("=" * 74)
    print(f"\nCensura a la derecha: se evalúa hasta {corte_periodo} (el dato llega a {ult};")
    print(f"nadie puede salir en {VENTANA_MESES} meses si solo quedan {VENTANA_MESES} meses de dato).")

    print(f"\nCarga\n  {m['alertas_mes']:.1f} alertas/mes notificadas "
          f"({m['alertas_evaluadas']:,} evaluables en la ventana no censurada)")

    print(f"\nPrecisión — de cada 100 alertas, cuántas preceden una salida en {VENTANA_MESES} meses")
    print(f"  salida lamentada    {100*m['precision_lamentada']:5.1f}%   "
          f"(base {100*m['base_lamentada']:.1f}%  ·  lift {m['lift_lamentada']:.2f}x)")
    print(f"  cualquier salida    {100*m['precision_cualquiera']:5.1f}%   "
          f"(base {100*m['base_cualquiera']:.1f}%  ·  lift {m['lift_cualquiera']:.2f}x)")

    print(f"\nCobertura — de las salidas lamentadas, a cuántas llegamos antes")
    print(f"  {m['cubiertas']} de {m['salidas_lamentadas']} = {100*m['cobertura']:.1f}%")

    print(f"\nCosto sobre quien se queda — la métrica que nadie muestra")
    print(f"  {m['quedan_alertados']:,} de {m['quedan']:,} = {100*m['carga_falsa']:.1f}% "
          f"apareció alguna vez en una alerta y sigue en Buk")

    techo = techo_de_cobertura(con)
    if techo is not None:
        techo["cobertura_pct"] = 100 * techo.cubiertas / techo.salidas_lamentadas
        sin_senal = techo[techo.perfil == "estable"]
        print("\nTecho de cobertura — por qué el número no puede ser mucho más alto")
        print(techo.to_string(index=False, float_format=lambda x: f"{x:6.1f}"))
        if len(sin_senal):
            pct = 100 * sin_senal.salidas_lamentadas.iloc[0] / techo.salidas_lamentadas.sum()
            print(f"\n  El {pct:.0f}% de las salidas lamentadas viene del perfil `estable`: gente sin")
            print("  deterioro previo por construcción. Ninguna regla —ni un modelo— la ve venir.")
            print(f"  Cobertura máxima alcanzable: ~{100-pct:.0f}%.")

    panel_dev = cobertura_panel_desarrollo(con)
    if panel_dev is not None:
        panel_dev["cobertura_pct"] = 100 * panel_dev.en_panel_desarrollo / panel_dev.total_personas
        print("\nAlcance del panel `desarrollo` — la mitad 'baja productividad' del mandato")
        print(panel_dev.to_string(index=False, float_format=lambda x: f"{x:6.1f}"))
        print("\n  v1.0.0 dejaba `bajo_desempeno` y `nuevo_dificil` en 0.0% en TODO canal.")
        print("  R06 los alcanza sin subir el ruido sobre `estable`/`estrella_subpagada`.")

    print("\nPoder de cada señal por separado (lift sobre la tasa base)")
    ls = lift_por_senal(con, cat)
    print(ls.to_string(index=False, float_format=lambda x: f"{x:7.2f}"))
    print("\n  La columna que importa es `lift_lamentada`. Compararla con `lift_cualquiera`")
    print("  muestra el sesgo que se evitó: las señales de bajo desempeño —descartadas del")
    print("  catálogo— brillan en la segunda columna y se hunden en la primera.")

    print("\nCurva de calibración — qué compra cada nivel de carga")
    curva = curva_de_calibracion(con, cat)
    print(curva.to_string(index=False, float_format=lambda x: f"{x:8.1f}"))
    op = cat["operacion"]["canales"]["conversacion"]
    print(f"\n  Punto elegido: cupo {op['cupo_mensual']}, enfriamiento {op['enfriamiento_meses']} meses.")
    print("  No maximiza ninguna columna. Es la capacidad real del equipo, y la tabla")
    print("  dice exactamente cuánta cobertura cuesta esa restricción.")

    con.close()
    return {"metricas": m, "senales": ls, "curva": curva, "techo": techo}


if __name__ == "__main__":
    main()
