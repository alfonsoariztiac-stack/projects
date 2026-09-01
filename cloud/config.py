"""
Coordenadas del proyecto GCP e identidad con la que se habla con BigQuery.

Dos ideas que este módulo sostiene y que se defienden en la sala:

1. **Una sola definición de dónde vive el dato.** Proyecto, dataset y región
   están escritos una vez. `southamerica-west1` no es un default: es la
   respuesta al argumento de residencia del dato del Eje 2 — la información de
   personas no sale de Chile.

2. **Sin archivo de credenciales en disco.** La identidad por defecto es el ADC
   del usuario (scope `cloud-platform`, sin nada de Drive). Cuando hace falta
   leer Sheets —F2 en adelante— no se agranda el scope del usuario: se cambia de
   identidad, impersonando una service account que solo ve una carpeta. No hay
   JSON de service account que se pueda filtrar.
"""

from __future__ import annotations

import os
import pathlib
import sys

import google.auth
from google.auth import impersonated_credentials
from google.cloud import bigquery

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SRC = RAIZ / "src"
SQL_DIR = SRC / "sql"

PROYECTO = os.environ.get("BQ_PROYECTO", "buk-people-alertas")
DATASET = os.environ.get("BQ_DATASET", "people_analytics")
REGION = os.environ.get("BQ_REGION", "southamerica-west1")

SERVICE_ACCOUNT = os.environ.get(
    "BQ_SERVICE_ACCOUNT",
    f"pipeline-alertas@{PROYECTO}.iam.gserviceaccount.com",
)

DATASET_ID = f"{PROYECTO}.{DATASET}"

SCOPE_GCP = "https://www.googleapis.com/auth/cloud-platform"
# Solo para la service account, y solo desde F2 (tablas externas sobre Sheets).
# La credencial personal nunca lo recibe.
SCOPE_DRIVE = "https://www.googleapis.com/auth/drive.readonly"


def usar_src() -> None:
    """Deja `src/` importable sin copiar ni un archivo del pipeline local.

    Todo lo que `cloud/` reutiliza —contratos, ingesta, tipado, calendario— se
    importa del original. Si mañana cambia una regla de calidad en `ingest.py`,
    la carga a BigQuery la hereda sin que nadie tenga que acordarse.
    """
    ruta = str(SRC)
    if ruta not in sys.path:
        sys.path.insert(0, ruta)


def credenciales(impersonar: bool = False, con_drive: bool = False):
    """Credencial del usuario (ADC) o de la service account, sin key en disco.

    La impersonación exige `roles/iam.serviceAccountTokenCreator` sobre la SA,
    que ya está concedido. El token se pide al vuelo y vive una hora.
    """
    fuente, _ = google.auth.default(scopes=[SCOPE_GCP])
    if not impersonar:
        return fuente
    alcance = [SCOPE_GCP] + ([SCOPE_DRIVE] if con_drive else [])
    return impersonated_credentials.Credentials(
        source_credentials=fuente,
        target_principal=SERVICE_ACCOUNT,
        target_scopes=alcance,
        lifetime=3600,
    )


def cliente(impersonar: bool = False, con_drive: bool = False) -> bigquery.Client:
    return bigquery.Client(
        project=PROYECTO,
        credentials=credenciales(impersonar, con_drive),
        location=REGION,
    )


def quien(cli: bigquery.Client) -> str:
    """Para que cada corrida diga en voz alta con qué identidad se conectó."""
    cred = cli._credentials
    return getattr(cred, "service_account_email", None) or getattr(
        cred, "_target_principal", None) or "ADC (usuario)"
