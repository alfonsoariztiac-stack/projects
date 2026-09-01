"""
Auditoría de impacto dispar: el contrapeso de la prohibición.

`motor.py` impide que un atributo protegido sea condición de una regla. Eso es
necesario y no basta: un sistema puede discriminar sin nombrar nunca al grupo
que discrimina, porque las variables que sí usa están correlacionadas con él.
La prohibición se compra con la obligación de medir.

Se miden dos cosas distintas, y la distinción importa más que los números:

    PARIDAD DEMOGRÁFICA — ¿alertamos a las mujeres tanto como a los hombres?
    Es la métrica intuitiva y es la equivocada por sí sola. Si un grupo tiene
    de verdad más riesgo, alertarlo más no es sesgo: es hacer el trabajo. Una
    desviación aquí abre una investigación, no cierra un juicio.

    IGUALDAD DE OPORTUNIDAD — de las personas de cada grupo que efectivamente
    renunciaron doliendo, ¿a qué fracción llegamos antes? Esta es la métrica
    ética real. Si el sistema cubre al 25% de un grupo y al 8% de otro, está
    repartiendo mal un beneficio, y eso es un defecto aunque las tasas de
    alerta sean idénticas.

    EXPOSICIÓN — nadie puede ser alertado un mes en que no era elegible. Un
    recién llegado está en el universo 6 meses; alguien con 4 años, 12. Medir
    alertas por persona los compara como si hubieran corrido la misma distancia.
    La tasa de alerta se calcula entonces por mes-persona expuesto, y es esa la
    que se contrasta contra el umbral.

El umbral es la regla del 80% (four-fifths rule, EEOC): un índice bajo 0,80 o
sobre 1,25 respecto del grupo de referencia se marca para revisión humana. No
es un veredicto automático, y por sí solo marca demasiado: con 26 salidas, una
persona cubierta de más mueve el índice 0,4. Por eso se exige además que la
diferencia contra el grupo de referencia supere lo que el azar binomial explica
(dos proporciones, |z| > 2). Marcar de más no es prudencia: entrena al comité a
ignorar la lista.

Se auditan también `job_family` y `pais_contrato`, que no son atributos
protegidos: si el 80% de las alertas cae en una familia de cargo, el problema
probablemente esté en la métrica operativa de esa familia, no en su gente.
"""

from __future__ import annotations

import pathlib
import sys

import duckdb
import pandas as pd
from math import sqrt

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from backtest import VENTANA_MESES, _preparar  # noqa: E402
from motor import cargar  # noqa: E402
from warehouse import BD  # noqa: E402

N_MINIMO = 40           # bajo esto el grupo se agrega: el ruido supera a la señal
SALIDAS_MINIMAS = 25    # bajo esto no se publica índice de cobertura
PISO, TECHO = 0.80, 1.25
Z_MINIMO = 2.0          # diferencia que el azar binomial no explica


def _z(exitos_a, n_a, exitos_b, n_b) -> float:
    """Test de dos proporciones. Cuánto se aleja la diferencia de lo esperable."""
    if not n_a or not n_b:
        return 0.0
    p = (exitos_a + exitos_b) / (n_a + n_b)
    se = sqrt(p * (1 - p) * (1 / n_a + 1 / n_b))
    return 0.0 if se == 0 else (exitos_a / n_a - exitos_b / n_b) / se

PROTEGIDOS = ["genero", "tramo_edad", "nacionalidad"]
GOBERNANZA = ["job_family", "pais_contrato", "tramo_antiguedad"]


def _panel(con: duckdb.DuckDBPyConnection, atributo: str, canal: str = "conversacion") -> pd.DataFrame:
    """Una fila por grupo: cuánta gente hay, a cuánta se alertó, a cuánta se llegó."""
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _grupo AS
        SELECT employee_id, MAX({atributo}) AS grupo
        FROM employee_360 GROUP BY employee_id
    """)
    # Los grupos pequeños se juntan en "otros (n < N_MINIMO)" antes de calcular
    # nada: publicar un índice sobre 12 personas invita a leer ruido como sesgo.
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _grupo_ajustado AS
        WITH tam AS (SELECT grupo, COUNT(*) n FROM _grupo GROUP BY grupo)
        SELECT g.employee_id,
               CASE WHEN t.n >= {N_MINIMO} THEN g.grupo
                    ELSE 'otros (n < {N_MINIMO})' END AS grupo
        FROM _grupo g JOIN tam t ON t.grupo = g.grupo
    """)
    return con.execute(f"""
        WITH dotacion AS (
          SELECT grupo, COUNT(*) AS personas FROM _grupo_ajustado GROUP BY grupo
        ),
        alertados AS (
          SELECT g.grupo,
                 COUNT(DISTINCT a.employee_id) AS alertados,
                 COUNT(*) AS alertas
          FROM alertas_bt a JOIN _grupo_ajustado g ON g.employee_id = a.employee_id
          WHERE a.canal = '{canal}' AND a.estado = 'notificada'
          GROUP BY g.grupo
        ),
        expuestos AS (
          -- Meses en que alguien del grupo era elegible: el denominador honesto.
          SELECT g.grupo, COUNT(*) AS meses_expuestos
          FROM universo_bt u JOIN _grupo_ajustado g ON g.employee_id = u.employee_id
          GROUP BY g.grupo
        ),
        salieron AS (
          SELECT g.grupo, COUNT(DISTINCT s.employee_id) AS salidas_lamentadas,
                 COUNT(DISTINCT CASE WHEN a.employee_id IS NOT NULL
                                     THEN s.employee_id END) AS cubiertas
          FROM salidas s
          JOIN _grupo_ajustado g ON g.employee_id = s.employee_id
          LEFT JOIN alertas_bt a
                 ON a.employee_id = s.employee_id AND a.estado = 'notificada'
                AND a.idx_mes BETWEEN s.idx_salida - {VENTANA_MESES} AND s.idx_salida - 1
          WHERE s.lamentada
          GROUP BY g.grupo
        )
        SELECT d.grupo, d.personas,
               COALESCE(a.alertados, 0) AS alertados,
               COALESCE(a.alertas, 0) AS alertas,
               COALESCE(e.meses_expuestos, 0) AS meses_expuestos,
               COALESCE(e.meses_expuestos, 0) * 1.0 / d.personas AS meses_expuesto,
               COALESCE(a.alertas, 0) * 1000.0
                 / NULLIF(e.meses_expuestos, 0) AS alertas_1000m,
               COALESCE(s.salidas_lamentadas, 0) AS salidas_lamentadas,
               COALESCE(s.salidas_lamentadas, 0) * 1.0 / d.personas AS tasa_salida,
               COALESCE(s.cubiertas, 0) AS cubiertas,
               COALESCE(s.cubiertas, 0) * 1.0 / NULLIF(s.salidas_lamentadas, 0) AS cobertura
        FROM dotacion d
        LEFT JOIN alertados a ON a.grupo = d.grupo
        LEFT JOIN expuestos e ON e.grupo = d.grupo
        LEFT JOIN salieron s ON s.grupo = d.grupo
        ORDER BY d.personas DESC
    """).df()


def auditar(con: duckdb.DuckDBPyConnection, atributo: str) -> pd.DataFrame:
    """Añade los dos índices y la marca de revisión.

    El grupo de referencia es el más numeroso, no el de mayor tasa: se compara
    contra la norma de la organización, que es lo que un comité puede discutir.
    """
    df = _panel(con, atributo)
    ref = df.iloc[0]
    df["indice_alerta"] = df.alertas_1000m / ref.alertas_1000m if ref.alertas_1000m else pd.NA
    df["indice_cobertura"] = df.cobertura / ref.cobertura if ref.cobertura else pd.NA
    # La cobertura de un grupo con 4 salidas salta entre 0 y 0,25 con una sola
    # persona. Publicar ese índice no es transparencia, es invitar a leer ruido
    # como sesgo: se anula y se dice que la muestra no alcanza.
    df.loc[df.salidas_lamentadas < SALIDAS_MINIMAS, ["cobertura", "indice_cobertura"]] = pd.NA

    # Dos condiciones, no una: el efecto tiene que ser grande (regla del 80%) y
    # tiene que ser real (no explicable por el tamaño de la muestra).
    df["z_alerta"] = [_z(f.alertas, f.meses_expuestos, ref.alertas, ref.meses_expuestos)
                      for _, f in df.iterrows()]
    df["z_cobertura"] = [_z(f.cubiertas, f.salidas_lamentadas,
                            ref.cubiertas, ref.salidas_lamentadas)
                         for _, f in df.iterrows()]

    def marcar(fila):
        fuera = []
        for nombre, col, z in [("alerta", "indice_alerta", "z_alerta"),
                               ("cobertura", "indice_cobertura", "z_cobertura")]:
            v = fila[col]
            if pd.notna(v) and not (PISO <= v <= TECHO) and abs(fila[z]) > Z_MINIMO:
                fuera.append(nombre)
        return "REVISAR: " + ", ".join(fuera) if fuera else "ok"

    df["estado"] = df.apply(marcar, axis=1)
    df.loc[df.index[0], "estado"] = "referencia"
    return df


def main() -> dict[str, pd.DataFrame]:
    cat = cargar()
    con = duckdb.connect(str(BD), read_only=True)
    _preparar(con, cat)

    print("=" * 78)
    print(f"AUDITORÍA DE IMPACTO DISPAR · catálogo v{cat['version']} · canal conversación")
    print("=" * 78)
    print(f"Se marca un grupo cuando el índice sale de [{PISO:.2f}, {TECHO:.2f}] (regla del 80%)")
    print(f"Y ADEMÁS la diferencia no se explica por azar binomial (|z| > {Z_MINIMO:.0f}).")
    print(f"Grupo de referencia: el más numeroso. Grupos con menos de {N_MINIMO} personas, agregados.")
    print(f"El índice de cobertura solo se publica con al menos {SALIDAS_MINIMAS} salidas lamentadas en el grupo.")
    print("\n  meses_expuesto   = meses promedio por persona en que fue elegible para alerta")
    print("  alertas_1000m    = alertas emitidas por cada 1.000 meses-persona expuestos")
    print("  indice_alerta    = alertas_1000m del grupo / las del grupo de referencia")
    print("  indice_cobertura = de quienes salieron doliendo, qué fracción alcanzamos,")
    print("                     relativa al grupo de referencia. ESTA es la métrica ética.")

    cols = ["grupo", "personas", "meses_expuesto", "alertas_1000m", "tasa_salida",
            "salidas_lamentadas", "cobertura",
            "indice_alerta", "indice_cobertura", "estado"]
    resultados, marcados = {}, []
    for titulo, atributos in [("ATRIBUTOS PROTEGIDOS", PROTEGIDOS),
                              ("EJES DE GOBERNANZA (no protegidos)", GOBERNANZA)]:
        print(f"\n\n{titulo}")
        for atributo in atributos:
            df = auditar(con, atributo)
            resultados[atributo] = df
            marcados += [(atributo, f.grupo, f.estado) for _, f in df.iterrows()
                         if str(f.estado).startswith("REVISAR")]
            print(f"\n· {atributo}")
            print(df[cols].to_string(index=False, float_format=lambda x: f"{x:7.3f}"))

    print("\n" + "=" * 78)
    if marcados:
        print(f"{len(marcados)} grupo(s) fuera de banda. No es un veredicto: es la lista de lo que")
        print("hay que mirar antes de publicar esta versión del catálogo.")
        for atributo, grupo, estado in marcados:
            print(f"  · {atributo:<18} {grupo:<22} {estado}")
        print("\nCómo se lee una desviación, en orden:")
        print("  1. ¿La tasa de salida real del grupo también es distinta? Entonces el sistema")
        print("     está siguiendo el riesgo, no creándolo, y no hay nada que corregir.")
        print("  2. ¿Hay una señal cuya métrica de origen se comporta distinto en ese grupo?")
        print("     (ej. productividad medida distinto en una familia de cargo).")
        print("  3. Recién entonces: revisar umbrales. Nunca añadir el atributo como condición.")
    else:
        print("Ningún grupo fuera de banda en esta corrida.")
    print("\nUn resultado limpio no prueba que el sistema sea justo: prueba que en ESTOS datos,")
    print("con ESTOS grupos y ESTE umbral, no se detectó impacto dispar. Se vuelve a correr en")
    print("cada cambio del catálogo, y el resultado se archiva con la versión.")

    con.close()
    return resultados


if __name__ == "__main__":
    main()
