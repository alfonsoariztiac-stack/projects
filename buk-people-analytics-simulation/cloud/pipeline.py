"""
Réplica de `motor.main()` contra BigQuery. `src/rules/motor.py` no se toca ni
una línea: lo único nuevo acá es la conexión (`adaptador.ConexionBQ`) y cómo se
guarda el resultado. Ninguna regla de negocio se reescribe — `compilar()`,
`ejecutar()` y `resumen()` son exactamente los mismos que corren local.

`employee_360` no necesita la SA impersonada con Drive: a diferencia de F2, es
una tabla nativa de BigQuery, no una external table sobre Sheets. Corre con la
identidad por defecto (ADC), igual que `correr_sql.py`.

Uso:
    uv run --project cloud python cloud/pipeline.py
    uv run --project cloud python cloud/pipeline.py --impersonar
"""

from __future__ import annotations

import argparse
import sys
import warnings

from google.cloud import bigquery

import adaptador
import config

# Mismo motivo que en cargar_bq.py: la advertencia sobre pandas-gbq no aporta
# nada en una corrida que se muestra en pantalla.
warnings.filterwarnings("ignore", message=".*pandas-gbq.*", category=FutureWarning)

config.usar_src()
sys.path.insert(0, str(config.SRC / "rules"))
import motor  # noqa: E402


def cargar_alertas(cli: bigquery.Client, df, verboso: bool = True) -> int:
    """Materializa `alertas` como tabla nativa. Sin esquema a mano.

    A diferencia de `stg_*`, estas columnas no vienen de un `CONTRATOS` — las
    calcula el motor (`nivel`, `regla_nombre`, `senales`, `evidencia`...) — así
    que no hay de dónde derivar un esquema. `autodetect` lo resuelve solo,
    incluso para `senales`/`evidencia`, que son listas: BigQuery las recibe
    como `STRING REPEATED` sin que haga falta declararlo (verificado con una
    carga de prueba antes de confiar en esto).
    """
    destino = f"{config.DATASET_ID}.alertas"
    cfg = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=True,
    )
    job = cli.load_table_from_dataframe(df, destino, job_config=cfg)
    job.result()
    n = cli.get_table(destino).num_rows
    if verboso:
        print(f"   {'alertas':<32} {n:>7,} filas · {len(df.columns):>2} columnas")
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--impersonar", action="store_true",
                    help="correr como la service account en vez de con tu ADC")
    ap.add_argument("--silencioso", action="store_true")
    args = ap.parse_args()
    verboso = not args.silencioso

    cat = motor.cargar()
    if verboso:
        print(f"Validando {motor.CATALOGO.relative_to(config.RAIZ)} ...")

    cli = config.cliente(impersonar=args.impersonar)
    if verboso:
        print(f"Identidad: {config.quien(cli)}")

    con = adaptador.ConexionBQ(cli)
    df = motor.ejecutar(cat, con)

    if verboso:
        print(f"\nCargando a {config.DATASET_ID} ({config.REGION}):")
    cargar_alertas(cli, df, verboso)

    motor.resumen(df, cat)
    if verboso:
        print(f"\nAlertas: tabla `alertas` en {config.DATASET_ID}")


if __name__ == "__main__":
    main()
