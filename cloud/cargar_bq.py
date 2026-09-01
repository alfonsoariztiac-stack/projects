"""
Carga a BigQuery: las mismas tablas del warehouse local, en el warehouse real.

El esquema de BigQuery **no se escribe a mano**: se deriva de `CONTRATOS`, la
misma declaración que ya valida los datos en la ingesta y que ya define los
tipos de pandas en `warehouse.PANDAS_TIPO`. Una sola definición de tipo, tres
usos —validación, DataFrame, DDL— y por lo tanto ninguna forma de que se
desincronicen.

El `mode` del campo tampoco es decorativo: una columna declarada `requerido` en
el contrato entra a BigQuery como `REQUIRED`. Si alguna vez la ingesta dejara
pasar un nulo donde el contrato prometió que no lo hay, la carga falla en vez de
escribirlo. El contrato viaja hasta el warehouse.

Lo que se reutiliza tal cual de `src/`, sin copiar una línea:
  · `ingest.ingestar()`   → los 9 DataFrames ya validados y con cuarentena aplicada
  · `warehouse.tipar()`   → los tipos del contrato aplicados al DataFrame
  · `warehouse.dim_periodos()` → el calendario de la ventana de análisis

Uso:
    uv run --project cloud python cloud/cargar_bq.py
    uv run --project cloud python cloud/cargar_bq.py --impersonar
"""

from __future__ import annotations

import argparse
import pathlib
import warnings

import pandas as pd
from google.cloud import bigquery

import config

# El cliente de BigQuery avisa que una versión futura preferirá pandas-gbq para
# cargar DataFrames. Es cierto y no es hoy: ensucia diez líneas la salida de una
# corrida que se muestra en pantalla.
warnings.filterwarnings("ignore", message=".*pandas-gbq.*", category=FutureWarning)

config.usar_src()
from contratos import CONTRATOS  # noqa: E402
import ingest  # noqa: E402
import warehouse  # noqa: E402

# La ingesta escribe las filas rechazadas a disco. Aquí se desvían fuera de
# `data/out/`: los artefactos de la corrida local son los que están validados y
# los que usa el deck, y una carga a BigQuery no tiene por qué tocarlos.
CUARENTENA = pathlib.Path(__file__).resolve().parent / ".cuarentena"

# Las 4 fuentes que hoy viven en Sheets (F2): en vez de abrir el XLSX de
# data/raw/, se leen desde `raw_*` en BigQuery — la external table que ve la
# celda editada al instante. Las 5 fuentes en CSV siguen leyendo data/raw/.
FUENTES_SHEETS = {"metricas_operativas", "cursos", "bitacora", "salidas"}

_LEER_LOCAL = ingest.leer  # referencia al original, antes de parchar nada


def leer_hibrido(cli_sheets: bigquery.Client):
    """Reemplazo de `ingest.leer()`: mismo contrato de retorno (un DataFrame
    con las columnas del contrato), pero para las 4 fuentes de Sheets el
    origen es `raw_*` en BigQuery en vez del XLSX local.

    `validar()` no distingue de dónde vino el DataFrame — la calidad de dato
    se aplica igual, editar la Sheet o editar el XLSX local tienen exactamente
    el mismo camino de validación.
    """
    def leer(nombre: str, contrato: dict) -> pd.DataFrame:
        if nombre not in FUENTES_SHEETS:
            return _LEER_LOCAL(nombre, contrato)
        # `create_bqstorage_client=False`: son miles de filas, no millones; no
        # vale la pena que la SA necesite además `bigquery.readSessionUser`.
        return cli_sheets.query(
            f"SELECT * FROM `{config.DATASET_ID}.raw_{nombre}`",
            location=config.REGION,
        ).to_dataframe(create_bqstorage_client=False)
    return leer

# El mismo mapeo de `warehouse.PANDAS_TIPO`, en el vocabulario de BigQuery.
BQ_TIPO = {
    "texto": "STRING",
    "numero": "FLOAT64",
    "entero": "INT64",
    "booleano": "BOOL",
    "periodo": "STRING",
    "fecha": "DATE",
}

# El calendario no viene de una fuente, se genera: es la única tabla cuyo
# esquema no puede salir de un contrato.
ESQUEMA_PERIODOS = [
    bigquery.SchemaField("periodo", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("idx_mes", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("anio", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("mes", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("fin_mes", "DATE", mode="REQUIRED"),
]


def glosa(spec: dict) -> str | None:
    """El resto del contrato —rangos, valores válidos, patrón— como descripción.

    BigQuery no sabe validar un CSAT entre 1 y 5, pero sí sabe mostrarlo. Quien
    abra el esquema en la consola ve la regla que la fila tuvo que cumplir para
    estar ahí, en vez de tener que ir a buscar el código.
    """
    partes = []
    if "valores" in spec:
        partes.append("valores: " + ", ".join(spec["valores"]))
    if "min" in spec or "max" in spec:
        partes.append(f"rango: [{spec.get('min', '−∞')}, {spec.get('max', '∞')}]")
    if "patron" in spec:
        partes.append(f"patrón: {spec['patron']}")
    if "largo_min" in spec:
        partes.append(f"largo mínimo: {spec['largo_min']}")
    return " · ".join(partes) or None


def esquema(nombre: str) -> list[bigquery.SchemaField]:
    """Traduce el contrato de una fuente al esquema de la tabla en BigQuery."""
    return [
        bigquery.SchemaField(
            col,
            BQ_TIPO[spec["tipo"]],
            mode="REQUIRED" if spec.get("requerido") else "NULLABLE",
            description=glosa(spec),
        )
        for col, spec in CONTRATOS[nombre]["columnas"].items()
    ]


def a_bigquery(df: pd.DataFrame, esq: list[bigquery.SchemaField]) -> pd.DataFrame:
    """Alinea el DataFrame con el esquema: mismas columnas, mismo orden.

    Las fechas se bajan de timestamp a `datetime.date`, que es lo que espera un
    campo DATE. Es la única conversión que la nube pide y que el warehouse local
    no necesitaba.
    """
    df = df[[campo.name for campo in esq]].copy()
    for campo in esq:
        if campo.field_type == "DATE":
            df[campo.name] = pd.to_datetime(df[campo.name]).dt.date
    return df


def cargar(cli: bigquery.Client, tabla: str, df: pd.DataFrame,
           esq: list[bigquery.SchemaField], verboso: bool = True,
           descripcion: str | None = None) -> int:
    destino = f"{config.DATASET_ID}.{tabla}"
    cfg = bigquery.LoadJobConfig(
        schema=esq,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        destination_table_description=descripcion,
    )
    job = cli.load_table_from_dataframe(a_bigquery(df, esq), destino, job_config=cfg)
    job.result()
    n = cli.get_table(destino).num_rows
    if verboso:
        print(f"   {tabla:<32} {n:>7,} filas · {len(esq):>2} columnas")
    return n


def construir(cli: bigquery.Client, verboso: bool = True) -> dict[str, int]:
    """Réplica de `warehouse.construir()` contra BigQuery, sin el SQL.

    Mismo conjunto de tablas y mismos nombres que en DuckDB: `stg_*` para las
    fuentes, `dim_periodos` para el calendario y `dim_cargos_v` como vista. Esa
    identidad de nombres es lo que permite que `src/sql/` corra sin una sola
    modificación en los dos motores.
    """
    ingest.CUARENTENA = CUARENTENA  # antes de ingestar: ver comentario arriba

    # Leer las Sheets siempre exige la SA impersonada con Drive, sin importar
    # con qué identidad se cargará el resultado a BigQuery más abajo — la
    # credencial personal nunca participa en esta lectura.
    cli_sheets = config.cliente(impersonar=True, con_drive=True)
    if verboso:
        print(f"Leyendo Sheets como: {config.quien(cli_sheets)}")
    ingest.leer = leer_hibrido(cli_sheets)
    try:
        tablas, _ = ingest.ingestar(verboso)
    finally:
        ingest.leer = _LEER_LOCAL

    if verboso:
        print(f"\nCargando a {config.DATASET_ID} ({config.REGION}):")

    conteos = {}
    for nombre, df in tablas.items():
        conteos[f"stg_{nombre}"] = cargar(
            cli, f"stg_{nombre}", warehouse.tipar(nombre, df), esquema(nombre), verboso,
            descripcion=CONTRATOS[nombre]["descripcion"])

    conteos["dim_periodos"] = cargar(
        cli, "dim_periodos", warehouse.dim_periodos(), ESQUEMA_PERIODOS, verboso,
        descripcion=f"Calendario mensual · ventana de {warehouse.MESES_VENTANA} "
                    f"meses al {warehouse.AS_OF}")

    cli.query(
        f"CREATE OR REPLACE VIEW `{config.DATASET_ID}.dim_cargos_v` AS "
        f"SELECT * FROM `{config.DATASET_ID}.stg_dim_cargos`",
        location=config.REGION,
    ).result()
    if verboso:
        print(f"   {'dim_cargos_v':<32} {'vista':>7}")
    return conteos


def main() -> dict[str, int]:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--impersonar", action="store_true",
                    help="cargar como la service account en vez de con tu ADC")
    ap.add_argument("--silencioso", action="store_true")
    args = ap.parse_args()

    verboso = not args.silencioso
    cli = config.cliente(impersonar=args.impersonar)
    if verboso:
        print(f"Identidad: {config.quien(cli)}")
    conteos = construir(cli, verboso)
    if verboso:
        print(f"\n{len(conteos)} tablas · {sum(conteos.values()):,} filas en BigQuery")
    return conteos


if __name__ == "__main__":
    main()
