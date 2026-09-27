#!/usr/bin/env bash
# DEMO 2, paso 4 — la redacción sobrevive hasta BigQuery.
# Las citas que la tarjeta de Chat muestra siguen diciendo [PERSONA_1]: el modelo
# nunca vio un nombre y lo que quedó guardado tampoco lo tiene.
set -euo pipefail
unset VIRTUAL_ENV   # si no, uv avisa que .venv no es cloud/.venv — ruido en pantalla
cd "$(dirname "$0")/../.."

uv run --project cloud python - <<'PYEOF'
import sys

sys.path.insert(0, "cloud")
import config

cli = config.cliente()
sql = f"""
SELECT employee_id, periodo, sentimiento, cita
FROM `{config.DATASET_ID}.bitacora_llm`, UNNEST(citas) AS cita
WHERE cita LIKE '%[PERSONA_%'
ORDER BY periodo DESC
LIMIT 3
"""
for fila in cli.query(sql, location=config.REGION):
    print(f"{fila.employee_id}  {fila.periodo}  {fila.sentimiento}  |  {fila.cita}")
PYEOF
