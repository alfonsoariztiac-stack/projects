# Se construye con el repo COMPLETO como contexto (`docker build -f cloud/Dockerfile .`
# desde la raíz, ver cloud/cloudbuild.yaml), no con `cloud/` solo: config.py calcula
# RAIZ como el padre de `cloud/` y `pipeline.py`/`cargar_bq.py` importan `src/` con ese
# mismo layout relativo. Reproducir esa relación de carpetas es más simple que
# reescribir cómo cada módulo encuentra sus imports.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /usr/local/bin/

WORKDIR /app

# `src/` y las 5 fuentes CSV (las 3 XLSX no hacen falta: esas 4 fuentes se leen
# de `raw_*` en BigQuery, no del archivo — ver cargar_bq.leer_hibrido()).
COPY src/ /app/src/
COPY data/raw/*.csv /app/data/raw/

# Dependencias primero (cache de Docker): solo se reinstalan si pyproject/lock
# cambian, no en cada edición de job.py.
COPY cloud/pyproject.toml cloud/uv.lock /app/cloud/
WORKDIR /app/cloud
RUN uv sync --locked --no-dev

# Glob explícito, no `COPY cloud/ .`: así nunca entran `.venv/`, `.cuarentena/`
# ni `__pycache__` locales a la imagen aunque existan en el disco de quien
# construye.
COPY cloud/*.py /app/cloud/

ENTRYPOINT ["uv", "run", "--locked", "python", "job.py"]
