"""
Checkpoint de F1 y F3: ¿BigQuery devuelve lo mismo que DuckDB?

`SELECT COUNT(*)` es el titular, pero no es una prueba: dos motores pueden
coincidir en el conteo y discrepar en cada promedio móvil. `comparar()` hace la
comparación **celda por celda**, alineando por una clave, y reporta por columna
cuántas filas difieren y cuál es la peor diferencia. Sirve para cualquier tabla
del dataset — `employee_360` (F1) y `alertas` (F3) la usan igual, cada una con
su propia clave, para no duplicar esta lógica dos veces.

Es el test severo de la migración: si el SQL es de verdad portable, esta salida
tiene que ser cero diferencias en todas las columnas. Cualquier otra cosa es una
diferencia de dialecto que no vimos.

No abre `buk.duckdb`: lee el Parquet exportado. Además de evitar el lock de
escritura de DuckDB, compara contra el mismo artefacto que consume el resto del
pipeline local, que es lo que interesa verificar.

Uso:
    uv run --project cloud python cloud/verificar.py
"""

from __future__ import annotations

import argparse
import datetime as dt

import numpy as np
import pandas as pd

import config

LOCAL_360 = config.RAIZ / "data" / "out" / "employee_360.parquet"
CLAVE_360 = ["employee_id", "idx_mes"]

# `alertas` no tiene una fila por (persona, mes) sino por (persona, mes, canal):
# una persona puede estar en panel de compensaciones y alertada en conversación
# el mismo período. Se verificó sin duplicados sobre el Parquet local antes de
# usarla como clave.
LOCAL_ALERTAS = config.RAIZ / "data" / "out" / "alertas.parquet"
CLAVE_ALERTAS = ["employee_id", "periodo", "canal"]

TOLERANCIA = 1e-9


def alinear(df: pd.DataFrame, columnas: list[str], clave: list[str]) -> pd.DataFrame:
    return df.sort_values(clave).reset_index(drop=True)[columnas]


def comparable(s: pd.Series) -> pd.Series:
    """Lleva una columna a una forma que se pueda comparar entre motores.

    Los dos lados traen la misma información con envases distintos —`Int64` vs
    `int64`, `dbdate` vs `datetime64`, `boolean` vs `object`—. Normalizar el
    envase antes de comparar evita reportar como diferencia lo que solo es una
    diferencia de tipo del cliente.
    """
    vivos = s.dropna()
    muestra = vivos.iloc[0] if len(vivos) else None
    # El Parquet devuelve los booleanos con nulos como `object`; BigQuery, como
    # `boolean`. Es el mismo dato en dos envases.
    if pd.api.types.is_bool_dtype(s) or isinstance(muestra, (bool, np.bool_)):
        return s.astype("boolean")
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce").astype("float64")
    if pd.api.types.is_datetime64_any_dtype(s) or isinstance(muestra, dt.date):
        return pd.to_datetime(s).astype("datetime64[ns]")
    # Columnas tipo lista (`senales`, `evidencia` en `alertas`): el Parquet
    # local trae `list`, BigQuery devuelve `numpy.ndarray` para un campo
    # REPEATED. Son el mismo dato en dos envases — igual que arriba — pero acá
    # además hay que normalizar antes de convertir a texto: `str(list)` y
    # `str(ndarray)` no se ven igual aunque el contenido sea idéntico
    # (comprobado antes de confiar en esto). Se lleva todo a `tuple`, que
    # compara por valor sin pasar por texto.
    if isinstance(muestra, (list, tuple, np.ndarray)):
        return s.map(lambda v: tuple(v) if v is not None else None)
    return s.astype("string")


def diferencias(a: pd.Series, b: pd.Series) -> tuple[int, float | None]:
    """Filas que difieren y peor diferencia numérica. Un nulo a cada lado coincide."""
    a, b = comparable(a), comparable(b)
    if pd.api.types.is_float_dtype(a) and pd.api.types.is_float_dtype(b):
        cerca = np.isclose(a.to_numpy(dtype="float64"), b.to_numpy(dtype="float64"),
                           rtol=TOLERANCIA, atol=TOLERANCIA, equal_nan=True)
        peor = float(np.nanmax(np.abs(a - b))) if (~cerca).any() else 0.0
        return int((~cerca).sum()), peor
    iguales = (a == b) | (a.isna() & b.isna())
    return int((~iguales).sum()), None


def comparar(cli, tabla: str, local: pd.DataFrame, clave: list[str],
             verboso: bool = True) -> pd.DataFrame:
    """Compara `tabla` en BigQuery contra `local`, celda a celda, alineando por `clave`.

    Generalizada a partir de la versión que solo comparaba `employee_360` (F1):
    `alertas` (F3) tiene otra clave natural — `local` y `clave` ahora entran
    como parámetros en vez de estar fijos en el módulo, así la lógica no se
    duplica para cada tabla nueva que se quiera verificar.
    """
    nube = cli.query(f"SELECT * FROM `{config.DATASET_ID}.{tabla}`",
                     location=config.REGION).to_dataframe()

    faltan, sobran = set(local.columns) - set(nube.columns), set(nube.columns) - set(local.columns)
    if faltan or sobran:
        raise SystemExit(f"Las columnas no coinciden. Faltan en BQ: {faltan or '—'} · "
                         f"Sobran en BQ: {sobran or '—'}")
    if len(local) != len(nube):
        raise SystemExit(f"Distinto número de filas: local {len(local):,} · BQ {len(nube):,}")

    columnas = list(local.columns)
    local, nube = alinear(local, columnas, clave), alinear(nube, columnas, clave)

    filas = []
    for col in columnas:
        n, peor = diferencias(local[col], nube[col])
        filas.append({"columna": col, "filas_distintas": n, "peor_diferencia": peor})
    rep = pd.DataFrame(filas)

    if verboso:
        print(f"{tabla} · {len(local):,} filas × {len(columnas)} columnas "
              f"· DuckDB (Parquet local) contra BigQuery\n")
        malas = rep[rep.filas_distintas > 0]
        if malas.empty:
            print("   Sin diferencias en ninguna columna.")
        else:
            print(f"   {len(malas)} columnas con diferencias:\n")
            for r in malas.itertuples():
                peor = "" if pd.isna(r.peor_diferencia) else f" · peor: {r.peor_diferencia:.3g}"
                print(f"   {r.columna:<32} {r.filas_distintas:>7,} filas{peor}")
    return rep


def inventario(cli, verboso: bool = True) -> pd.DataFrame:
    """Qué hay en el dataset y con cuántas filas. El estado, en una tabla."""
    sql = f"""
    SELECT table_name AS objeto, table_type AS tipo, IFNULL(row_count, 0) AS filas
    FROM `{config.PROYECTO}.{config.DATASET}.__TABLES__` t
    JOIN `{config.PROYECTO}.{config.DATASET}.INFORMATION_SCHEMA.TABLES` i
      ON i.table_name = t.table_id
    ORDER BY tipo, objeto
    """
    df = cli.query(sql, location=config.REGION).to_dataframe()
    if verboso:
        print(f"\n{config.DATASET_ID} · {len(df)} objetos\n")
        for r in df.itertuples():
            marca = "vista" if r.tipo == "VIEW" else f"{r.filas:,} filas"
            print(f"   {r.objeto:<32} {marca:>14}")
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--impersonar", action="store_true")
    ap.add_argument("--solo", choices=["employee_360", "alertas"],
                    help="verificar una sola tabla (por defecto, las dos)")
    args = ap.parse_args()

    cli = config.cliente(impersonar=args.impersonar)
    inventario(cli)

    tablas = [args.solo] if args.solo else ["employee_360", "alertas"]
    total_general = 0
    for tabla in tablas:
        local, clave = ((LOCAL_360, CLAVE_360) if tabla == "employee_360"
                        else (LOCAL_ALERTAS, CLAVE_ALERTAS))
        print()
        rep = comparar(cli, tabla, pd.read_parquet(local), clave)
        total = int(rep.filas_distintas.sum())
        total_general += total
        print(f"\n{'PASA' if total == 0 else 'FALLA'} · {tabla} · {total:,} "
              f"celdas distintas entre los dos motores")

    if "alertas" in tablas:
        # El test explícito que pide el plan de F3 ("Verificación end-to-end",
        # paso 4): candidatas por canal, la cifra que se repite en la sala
        # (conversacion 696 · compensaciones 773 · desarrollo 593). La
        # comparación celda a celda de arriba ya lo implica —si no hay ninguna
        # fila distinta, el conteo por canal tampoco puede diferir— pero se
        # imprime aparte porque es la cifra concreta que se compara a ojo.
        nube = cli.query(
            f"SELECT canal, COUNT(*) AS candidatas FROM `{config.DATASET_ID}.alertas` "
            "GROUP BY canal ORDER BY canal", location=config.REGION).to_dataframe()
        print("\nCandidatas por canal (en BigQuery):")
        for r in nube.itertuples():
            print(f"   {r.canal:<15} {r.candidatas:>5,}")

    if len(tablas) > 1:
        print(f"\n{'PASA' if total_general == 0 else 'FALLA'} · total · "
              f"{total_general:,} celdas distintas entre los dos motores")


if __name__ == "__main__":
    main()
