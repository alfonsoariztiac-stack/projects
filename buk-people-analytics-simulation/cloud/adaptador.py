"""
Adaptador para que `motor.ejecutar()` hable con BigQuery igual que con DuckDB.

`motor.ejecutar()` no sabe ni le importa de dónde viene `con`: solo le pide
`con.execute(sql).df()`. Esa es la superficie mínima que hay que imitar — no se
replica el resto de la API de DuckDB (`fetchone`, `fetchall`, `executemany`...)
porque nada de lo que corre en la nube los usa. Se comprobó con `grep` sobre
`cloud/` y `src/` antes de escribir esto: lo único que llama `.fetchone()` son
`warehouse.py`, `catalogo.py`, `backtest.py` y `documentar.py`, ninguno de los
cuales migra (son las herramientas de auditoría offline, fuera de alcance por
diseño — ver `README.md`).

## Cómo se resuelve `employee_360` sin calificar el nombre en el texto

`motor.compilar(cat)` genera un `SELECT` plano, nunca una vista. Eso importa
porque el problema que `correr_sql.py::calificar()` resuelve en F1 es
específico de `CREATE VIEW`: BigQuery no recuerda el dataset por defecto de la
sesión que creó la vista. Un `SELECT` normal no tiene ese problema —
`QueryJobConfig(default_dataset=...)` alcanza y se probó antes de asumirlo
(`SELECT COUNT(*) FROM employee_360` sin calificar, contra el dataset real,
devolvió 31.954). La ventaja sobre `calificar()`: el texto que efectivamente
se envía a BigQuery es el mismo, carácter por carácter, que el que se guarda en
`data/out/alertas.sql` — no hay backticks ni rutas intercaladas.
"""

from __future__ import annotations

import pandas as pd
from google.cloud import bigquery

import config


class ResultadoBQ:
    """Envuelve un job ya terminado. Solo expone lo que `motor.ejecutar()` pide."""

    def __init__(self, job: bigquery.QueryJob):
        self._job = job

    def df(self) -> pd.DataFrame:
        # `create_bqstorage_client=False`: son miles de filas, no millones — el
        # mismo criterio que ya usa `cargar_bq.py` para no pedir el permiso de
        # Storage API por una lectura de este tamaño.
        return self._job.to_dataframe(create_bqstorage_client=False)


class ConexionBQ:
    """Habla el dialecto mínimo que `motor.ejecutar()` le pide a DuckDB."""

    def __init__(self, cli: bigquery.Client):
        self.cli = cli

    def execute(self, sql: str) -> ResultadoBQ:
        cfg = bigquery.QueryJobConfig(default_dataset=config.DATASET_ID)
        job = self.cli.query(sql, job_config=cfg, location=config.REGION)
        job.result()
        return ResultadoBQ(job)
