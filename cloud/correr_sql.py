"""
Ejecuta `src/sql/*.sql` en BigQuery. Los archivos no se tocan.

Este módulo es la prueba de la afirmación que sostiene el diseño del modelo de
datos: *"migrar a producción es cambiar el conector y el nombre del dataset; el
SQL no"*. No hay reescritura, ni plantillas, ni un `if motor == 'bigquery'`. Hay
un `read_text()`, una sustitución de nombres y un `client.query()`.

## La única diferencia de dialecto que apareció

Se auditaron y probaron contra BigQuery las construcciones sospechosas —
`CAST(... AS INTEGER)`, cláusula `WINDOW` con nombre, `LAST_VALUE(... IGNORE
NULLS)`, ventanas `ROWS BETWEEN`, `EXTRACT`— y todas corren igual que en DuckDB.
La aritmética de meses por `idx_mes` hizo su trabajo: no hubo que tocar una
línea de lógica.

Lo que sí difiere es de motor, no de lenguaje: **BigQuery no guarda el dataset
por defecto dentro de la definición de una vista**. Un `CREATE VIEW` cuyo cuerpo
diga `FROM dim_periodos` es rechazado, aunque el job traiga `default_dataset`
seteado. Y si se crea dentro de una sesión con `SET @@dataset_id`, BigQuery lo
acepta y deja una vista rota que falla al consultarla desde fuera —peor que el
error. Probado y descartado.

La salida es calificar los nombres al ejecutar, no editar el archivo:
`dim_periodos` → `` `buk-people-alertas.people_analytics.dim_periodos` ``. La
lista de qué calificar **no está escrita a mano**: sale de `CONTRATOS` (las
fuentes) y de los propios `CREATE OR REPLACE` de los archivos (los derivados).
Si mañana se agrega una vista al pipeline, se califica sola.

Uso:
    uv run --project cloud python cloud/correr_sql.py
    uv run --project cloud python cloud/correr_sql.py --mostrar 01_persona_mes.sql
    uv run --project cloud python cloud/correr_sql.py --dry-run   # solo re-valida
"""

from __future__ import annotations

import argparse
import pathlib
import re

from google.cloud import bigquery

import config

config.usar_src()
from contratos import CONTRATOS  # noqa: E402

# Los objetos que el propio pipeline crea, leídos de los archivos.
CREACION = re.compile(r"CREATE\s+OR\s+REPLACE\s+(?:VIEW|TABLE)\s+([A-Za-z_]\w*)", re.I)


def archivos() -> list[pathlib.Path]:
    """Orden alfabético = orden de dependencias. El prefijo numérico es el plan."""
    return sorted(config.SQL_DIR.glob("*.sql"))


def objetos() -> set[str]:
    """Todo lo que vive en el dataset: las fuentes cargadas y lo que el SQL deriva.

    Ninguno de estos nombres choca con los alias de CTE de los archivos (`base`,
    `persona`, `ev`, `acumulado`…), que es justo lo que permite calificar por
    nombre sin tener que parsear SQL de verdad.
    """
    derivados = {n for a in archivos() for n in CREACION.findall(a.read_text("utf-8"))}
    fuentes = {f"stg_{n}" for n in CONTRATOS} | {"dim_periodos", "dim_cargos_v"}
    return derivados | fuentes


def calificar(sql: str, nombres: set[str] | None = None) -> str:
    """Antepone proyecto y dataset a los nombres del pipeline, fuera de comentarios.

    Los comentarios se dejan intactos a propósito: son la mitad del valor de
    estos archivos y quien abra la vista en la consola de BigQuery debe leer el
    mismo texto que está en el repositorio, no una versión con rutas dentro.
    """
    patron = re.compile(r"\b(" + "|".join(sorted(nombres or objetos())) + r")\b")
    reemplazo = lambda m: f"`{config.DATASET_ID}.{m.group(1)}`"  # noqa: E731

    lineas = []
    for linea in sql.splitlines():
        # Estos archivos no tienen literales con `--` ni comentarios de bloque.
        codigo, sep, comentario = linea.partition("--")
        lineas.append(patron.sub(reemplazo, codigo) + sep + comentario)
    return "\n".join(lineas)


def correr(cli: bigquery.Client, dry_run: bool = False, verboso: bool = True) -> int:
    """Corre el lote. Devuelve los bytes facturados (0 en dry-run: no se cobra)."""
    nombres, total = objetos(), 0
    for archivo in archivos():
        sql = calificar(archivo.read_text("utf-8"), nombres)
        cfg = bigquery.QueryJobConfig(dry_run=dry_run, use_query_cache=not dry_run)
        job = cli.query(sql, job_config=cfg, location=config.REGION)
        if not dry_run:
            job.result()
        facturado = job.total_bytes_processed if dry_run else job.total_bytes_billed
        total += facturado or 0
        if verboso:
            print(f"   {archivo.name:<28} {'valida' if dry_run else 'ok':<7} {mib(facturado)}")
    return total


def mib(n: int | None) -> str:
    return f"{(n or 0) / 1024 / 1024:>8.1f} MiB"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="valida y estima el costo sin ejecutar. Solo sirve si las "
                         "vistas ya existen: un archivo no ve lo que crearía el anterior")
    ap.add_argument("--mostrar", metavar="ARCHIVO",
                    help="imprime el SQL calificado que se enviaría, sin conectarse")
    ap.add_argument("--impersonar", action="store_true")
    ap.add_argument("--silencioso", action="store_true")
    args = ap.parse_args()

    if args.mostrar:
        print(calificar((config.SQL_DIR / args.mostrar).read_text("utf-8")))
        return 0

    verboso = not args.silencioso
    cli = config.cliente(impersonar=args.impersonar)
    if verboso:
        modo = "Validando" if args.dry_run else "Ejecutando"
        print(f"{modo} {len(archivos())} archivos de src/sql/ "
              f"sobre {config.DATASET_ID} · identidad: {config.quien(cli)}")
    total = correr(cli, args.dry_run, verboso)
    if verboso:
        etiqueta = "procesados (estimado)" if args.dry_run else "facturados"
        print(f"\n   {'total':<28} {'':<7} {mib(total)} {etiqueta}")
    return total


if __name__ == "__main__":
    main()
