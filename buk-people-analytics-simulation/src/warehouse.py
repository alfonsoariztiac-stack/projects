"""
Warehouse local: DuckDB haciendo de BigQuery.

El SQL de `src/sql/` está escrito en el subconjunto que BigQuery y DuckDB
interpretan igual —sin DATE_DIFF, sin DATE_TRUNC, sin SAFE_CAST— de modo que no
existe capa de traducción entre lo que se muestra y lo que correría en el
warehouse de Buk. Toda la aritmética de meses pasa por `idx_mes`, un entero.

Migrar a producción es cambiar el conector y el nombre del dataset. El SQL no.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import sys

import duckdb
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from contratos import CONTRATOS  # noqa: E402
from ingest import RAIZ, SALIDA, escribir_reporte, ingestar  # noqa: E402

SQL_DIR = pathlib.Path(__file__).parent / "sql"
BD = SALIDA / "buk.duckdb"

AS_OF = dt.date(2026, 8, 31)
MESES_VENTANA = 18

PANDAS_TIPO = {"texto": "string", "numero": "float64", "entero": "Int64",
               "booleano": "boolean", "periodo": "string"}


def tipar(nombre: str, df: pd.DataFrame) -> pd.DataFrame:
    """Aplica al DataFrame los tipos que declara el contrato.

    El contrato ya dijo de qué tipo es cada columna al validarla; sería absurdo
    volver a adivinarlo aquí. Una sola definición de tipo, dos usos.
    """
    df = df.copy()
    for col, spec in CONTRATOS[nombre]["columnas"].items():
        if spec["tipo"] == "fecha":
            df[col] = pd.to_datetime(df[col], errors="coerce")
        else:
            df[col] = df[col].astype(PANDAS_TIPO[spec["tipo"]])
    return df


def dim_periodos(fin: dt.date = AS_OF, n: int = MESES_VENTANA) -> pd.DataFrame:
    """Calendario mensual. En BigQuery esto sería una tabla del dataset común.

    Tener el calendario como tabla, en vez de generarlo con GENERATE_DATE_ARRAY,
    hace el SQL portable y además deja la ventana de análisis como un dato
    auditable en vez de un literal escondido en una consulta.
    """
    filas = []
    for k in range(n - 1, -1, -1):
        idx = (fin.year * 12 + fin.month - 1) - k
        anio, mes = divmod(idx, 12)
        mes += 1
        fin_mes = (dt.date(anio + (mes == 12), (mes % 12) + 1, 1) - dt.timedelta(days=1))
        filas.append({"periodo": f"{anio:04d}-{mes:02d}", "idx_mes": idx,
                      "anio": anio, "mes": mes, "fin_mes": fin_mes})
    df = pd.DataFrame(filas)
    df["fin_mes"] = pd.to_datetime(df["fin_mes"])
    return df


def construir(tablas: dict[str, pd.DataFrame], verboso: bool = True) -> duckdb.DuckDBPyConnection:
    BD.parent.mkdir(parents=True, exist_ok=True)
    if BD.exists():
        BD.unlink()
    con = duckdb.connect(str(BD))

    for nombre, df in tablas.items():
        con.register(f"_{nombre}", tipar(nombre, df))
        con.execute(f"CREATE OR REPLACE TABLE stg_{nombre} AS SELECT * FROM _{nombre}")
    con.register("_periodos", dim_periodos())
    con.execute("CREATE OR REPLACE TABLE dim_periodos AS SELECT * FROM _periodos")
    con.execute("CREATE OR REPLACE VIEW dim_cargos_v AS SELECT * FROM stg_dim_cargos")

    for archivo in sorted(SQL_DIR.glob("*.sql")):
        con.execute(archivo.read_text(encoding="utf-8"))
        if verboso:
            print(f"   {archivo.name}")
    return con


def resumen(con: duckdb.DuckDBPyConnection) -> None:
    q = lambda s: con.execute(s).fetchone()[0]  # noqa: E731
    ult = q("SELECT MAX(periodo) FROM employee_360")
    print(f"\nemployee_360: {q('SELECT COUNT(*) FROM employee_360'):,} filas · "
          f"{q('SELECT COUNT(DISTINCT employee_id) FROM employee_360'):,} personas · "
          f"{q('SELECT COUNT(DISTINCT periodo) FROM employee_360')} meses "
          f"({q('SELECT MIN(periodo) FROM employee_360')} a {ult})")
    activos = q("SELECT COUNT(*) FROM employee_360 "
                f"WHERE periodo = '{ult}' AND activo_en_el_mes")
    print(f"activos en {ult}: {activos:,}")


def main(verboso: bool = True) -> duckdb.DuckDBPyConnection:
    tablas, rep = ingestar(verboso)
    escribir_reporte(rep)
    if verboso:
        print("\nConstruyendo el modelo:")
    con = construir(tablas, verboso)
    salida = SALIDA / "employee_360.parquet"
    con.execute(f"COPY employee_360 TO '{salida}' (FORMAT PARQUET)")
    if verboso:
        resumen(con)
        print(f"\nModelo: {BD.relative_to(RAIZ)} · export: {salida.relative_to(RAIZ)}")
    return con


if __name__ == "__main__":
    main()
