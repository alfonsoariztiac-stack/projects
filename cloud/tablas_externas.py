"""
Las 3 planillas como external tables `raw_*` sobre Google Sheets.

Esquema **explícito** (todo STRING), no autodetect. Dos razones concretas:

1. **Control del nombre de columna.** Autodetect leería el header real de la
   planilla — "ID Colaborador", "Mes ", "Productividad %", "CSAT (1-5)" — y esos
   no son identificadores válidos en BigQuery sin backticks incómodos en cada
   query. Con esquema explícito elegimos el nombre.
2. **Estabilidad de tipo.** Si mañana alguien escribe "94,4" en vez de "94.4" en
   una celda de productividad, autodetect podría inferir STRING para toda la
   columna y romper silenciosamente todo lo que la trata como número aguas
   abajo. Con STRING fijo, esa conversión es responsabilidad explícita del
   contrato (`ingest.validar()` en `cargar_bq.py`), no una inferencia que puede
   cambiar de una corrida a otra.

Decisión de nombres (discutida con Alfonso, 2026-09-01): los campos de `raw_*`
usan el **vocabulario final del contrato** (`employee_id`, `periodo`, `csat`...),
no el header sucio del Excel. Lo "crudo" de estas tablas está en los *valores*
— comas decimales, 3 formatos de fecha, duplicados, huérfanos — no en el
nombre de columna, que de todas formas nunca se lee del archivo porque el
esquema es explícito. `cargar_bq.py` corre el contrato entre `raw_*` y
`stg_*`, y esa validación es visible: es un paso real, no una promesa.

## Lo único que hay que mantener a mano

`skip_leading_rows` salta el header, así que el esquema es **posicional**: el
campo N de `COLUMNAS_FISICAS` tiene que ser la columna N física de la hoja. Si
alguien reordena columnas en la planilla, esta tabla queda mal etiquetada sin
error — es el costo real de una external table sobre una hoja de cálculo que
mantiene una persona a mano, y vale la pena decirlo así en la sala.

Uso:
    uv run --project cloud python cloud/tablas_externas.py
"""

from __future__ import annotations

import argparse

from google.cloud import bigquery

import config

config.usar_src()
from contratos import CONTRATOS  # noqa: E402

# Un Sheet por archivo del contrato. `gs_desarrollo_bitacora.xlsx` es un solo
# Sheet con dos hojas (cursos y bitácora), por eso son 3 IDs para 4 fuentes.
SHEET_IDS = {
    "gs_metricas_operativas.xlsx": "1jHVCV2F7zWynUwakm_-cpwbyLqZdkNzdUoe0cbla9Es",
    "gs_historico_salidas.xlsx": "1eN1vGl63t2lN_VsmR_heuvb911Kfyc5Wb_kzlEquCj0",
    "gs_desarrollo_bitacora.xlsx": "1T9ujCnvHxKWCuBr73NZ7KPVAOlI8pkLIUVmCHZXofHE",
}

# El orden físico exacto de columnas en cada hoja. No sale de `CONTRATOS`
# porque un dict de Python no promete el orden de las columnas en un Excel —
# `hoja` y `archivo` sí se reutilizan desde ahí, ver `fuentes()`.
COLUMNAS_FISICAS = {
    "metricas_operativas": [
        "employee_id", "periodo", "productividad_pct",
        "dias_sin_vacaciones", "csat", "nps_proceso",
    ],
    "salidas": [
        "employee_id", "fecha_salida", "tipo_salida", "motivo_declarado",
        "salida_lamentada", "meses_en_buk", "texto_entrevista_salida",
    ],
    "cursos": [
        # "plataforma" no vive en el contrato: se declara igual, para que se
        # vea en la consola que la tabla cruda trae una columna que el
        # contrato descarta a propósito.
        "employee_id", "curso", "fecha_finalizacion", "horas", "plataforma",
    ],
    "bitacora": [
        "employee_id", "fecha", "autor_hrbp", "tipo_instancia", "nota",
    ],
}


def fuentes() -> dict[str, dict]:
    """Combina `CONTRATOS` (archivo, hoja) con `COLUMNAS_FISICAS` (posición)."""
    return {
        nombre: {
            "sheet_id": SHEET_IDS[CONTRATOS[nombre]["archivo"]],
            "hoja": CONTRATOS[nombre].get("hoja"),
            "columnas": COLUMNAS_FISICAS[nombre],
        }
        for nombre in COLUMNAS_FISICAS
    }


def rango(hoja: str | None, n_columnas: int) -> str | None:
    """`'Hoja'!A1:E200000`, o `None` para la hoja única (BigQuery usa la primera)."""
    if not hoja:
        return None
    ultima = chr(ord("A") + n_columnas - 1)
    return f"'{hoja}'!A1:{ultima}200000"


def definicion(nombre: str, spec: dict) -> bigquery.Table:
    tabla = bigquery.Table(f"{config.DATASET_ID}.raw_{nombre}")
    tabla.schema = [bigquery.SchemaField(c, "STRING") for c in spec["columnas"]]

    externa = bigquery.ExternalConfig("GOOGLE_SHEETS")
    externa.source_uris = [f"https://docs.google.com/spreadsheets/d/{spec['sheet_id']}"]
    externa.google_sheets_options.skip_leading_rows = 1
    if r := rango(spec["hoja"], len(spec["columnas"])):
        externa.google_sheets_options.range = r
    tabla.external_data_configuration = externa

    hoja = f" · hoja {spec['hoja']!r}" if spec["hoja"] else ""
    tabla.description = (
        f"Cruda, sin validar, sobre Google Sheets ({CONTRATOS[nombre]['archivo']}{hoja}). "
        f"El contrato corre entre esta tabla y `stg_{nombre}` — ver cargar_bq.py."
    )
    return tabla


def crear(cli: bigquery.Client, verboso: bool = True) -> dict[str, int]:
    """Crea (o reemplaza) las 4 external tables y confirma con una lectura real.

    La creación en sí no toca Drive — es metadata. La cuenta de filas que
    sigue sí, y es la prueba de que el acceso compartido a la carpeta
    funciona de punta a punta, no solo que el permiso IAM está bien puesto.
    """
    conteos = {}
    for nombre, spec in fuentes().items():
        destino = f"raw_{nombre}"
        cli.delete_table(f"{config.DATASET_ID}.{destino}", not_found_ok=True)
        cli.create_table(definicion(nombre, spec))
        # `create_bqstorage_client=False`: la SA no tiene (ni necesita)
        # `bigquery.readSessionUser` — son filas de a miles, no de a millones,
        # y no vale la pena un permiso extra por una lectura de este tamaño.
        fila = next(iter(cli.query(
            f"SELECT COUNT(*) AS n FROM `{config.DATASET_ID}.{destino}`",
            location=config.REGION,
        ).result()))
        conteos[destino] = int(fila.n)
        if verboso:
            hoja = spec["hoja"] or "(hoja única)"
            print(f"   {destino:<28} {fila.n:>7,} filas · {len(spec['columnas']):>2} columnas · {hoja}")
    return conteos


def main() -> dict[str, int]:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--silencioso", action="store_true")
    args = ap.parse_args()

    verboso = not args.silencioso
    # Siempre impersonada y con Drive: es la única identidad autorizada a leer
    # la carpeta compartida. No hay flag `--impersonar` aquí porque no hay
    # alternativa — la credencial personal de Alfonso nunca tiene este scope.
    cli = config.cliente(impersonar=True, con_drive=True)
    if verboso:
        print(f"Identidad: {config.quien(cli)}\n")
    conteos = crear(cli, verboso)
    if verboso:
        print(f"\n{len(conteos)} external tables · {sum(conteos.values()):,} filas leídas desde Sheets")
    return conteos


if __name__ == "__main__":
    main()
