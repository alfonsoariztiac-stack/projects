# Alertas Tempranas de People Happiness (caso práctico Buk)

Simulación funcional de un sistema de alertas tempranas para equipos de People Happiness /
RRHH: cruza datos de desempeño, compensación, métricas operativas y notas cualitativas de
seguimiento, y dispara alertas de riesgo de desvinculación o baja productividad directamente a
Google Chat, de forma autónoma y mensual.

Construida en respuesta al caso práctico técnico de un proceso de selección (Buk, "People Data
& Automation Specialist"): pedían una propuesta en 5 láminas, y terminé construyendo la
arquitectura completa como si fuera a producción, con una versión local validada en DuckDB y
su réplica exacta en Google Cloud (BigQuery + Cloud Run + Cloud Scheduler), verificada celda
por celda entre ambos motores.

No avancé en ese proceso de selección. Pero después de 3 días enteros programando esto, no iba
a dejar que se fuera a la basura, así que acá está, como una muestra más de lo que soy capaz de
armar cuando me dan un problema real.

## El problema

El equipo de People Happiness pierde hasta 15 horas semanales cruzando manualmente planillas de
Google Sheets (evaluaciones de desempeño, datos salariales, métricas operativas) para
identificar colaboradores en riesgo, además de leer a mano cientos de notas cualitativas de
reuniones de seguimiento. El proceso es lento, propenso a error humano y reactivo.

## La solución

Un pipeline que integra las fuentes declaradas por el caso (BigQuery, Google Sheets, Google
Docs), procesa las notas cualitativas con un LLM, y aplica un catálogo de reglas de negocio
versionado para decidir qué colaboradores generan una alerta, evitando sesgo punitivo y
estigmatización por diseño, no solo de palabra.

Se construyó primero una simulación 100% local (DuckDB, datos sintéticos con `faker`/`numpy`,
sin ninguna dependencia externa) para validar la lógica de negocio sin fricción, y luego se
migró 1:1 a Google Workspace, en fases:

| Fase | Qué hace |
|---|---|
| F1 | `employee_360` replicado en BigQuery, verificado celda por celda contra el parquet local (0 diferencias en ~1,75M celdas) |
| F2 | Las 3 planillas de Sheets entran como external tables y se normalizan con el mismo contrato de validación que corre local |
| F3 | El motor de reglas corre contra BigQuery reusando el mismo código Python que corre local, sin reescribir una línea |
| F4 | Las alertas se postean como tarjetas reales en Google Chat |
| F5 | Las notas de seguimiento se leen en vivo desde Google Docs |
| F6 | Cloud Run Job + Cloud Scheduler orquestan el pipeline completo (carga → SQL → reglas → enriquecimiento con IA → Chat) una vez al mes, sin intervención humana |
| F7 | Vistas SQL para un dashboard en Looker Studio |

El SQL se escribió desde el día 1 en el subconjunto común entre DuckDB y BigQuery (evitando
`DATE_DIFF`, `DATE_TRUNC` y `SAFE_CAST`, que tienen firmas distintas en cada motor), así que
migrar de local a cloud fue cambiar el conector, no reescribir lógica.

### Los 4 ejes del caso

1. **Arquitectura y flujo de datos**: pipeline ETL automatizado de punta a punta (tabla arriba),
   orquestado mensualmente sin intervención manual.
2. **IA para productividad interna**: las notas de las reuniones de seguimiento se redactan
   (`src/llm/scrubber.py`) antes de salir hacia el LLM: nombres, RUTs y montos se reemplazan
   por marcadores antes de cualquier llamada externa. Las respuestas se cachean por hash del
   texto ya redactado, así que la misma nota nunca se vuelve a mandar dos veces.
3. **Reglas de negocio y gobernanza**: el catálogo de alertas vive en `src/rules/reglas.yaml`,
   versionado y documentado (`REGLAS.md`, autogenerado desde el propio YAML), no hardcodeado en
   código. `src/rules/backtest.py` y `src/rules/equidad.py` verifican calibración e impacto
   disparejo entre grupos antes de dar por buena una regla.
4. **Interfaz, ética y acción**: la tarjeta que recibe el Happiness Manager (`src/deliver/chat_card.py`)
   está diseñada para dar contexto accionable sin exponer un puntaje punitivo de la persona.

## Stack técnico

- **Local**: Python, DuckDB, Pandas, `faker` (datos sintéticos)
- **Cloud**: BigQuery, Cloud Run Jobs, Cloud Scheduler, Cloud Build, Google Chat API, Google
  Docs/Drive API, Looker Studio
- **IA**: Gemini (`google-genai`), con redacción de PII previa a cualquier llamada
- **Gestión de dependencias**: `uv`, dos proyectos independientes (raíz para local, `cloud/`
  para la parte GCP) que no se pisan entre sí

## Cómo correrlo

Simulación local, sin credenciales de ningún tipo:

```bash
uv sync
uv run python src/generate_data.py   # datos sintéticos
uv run python src/warehouse.py       # carga a DuckDB
uv run python src/rules/motor.py     # motor de reglas -> alertas.parquet
uv run python src/deliver/chat_card.py
uv run python deck/construir.py      # deck de 5 láminas
```

La parte cloud (`cloud/`) requiere un proyecto de GCP propio y credenciales de Google Workspace;
ver [`cloud/README.md`](cloud/README.md) para el detalle de cada fase.

Documentación completa del ambiente de datos y del catálogo de reglas en [`DATOS.md`](DATOS.md)
y [`REGLAS.md`](REGLAS.md).

## Estado

Simulación completa y presentada. Todos los datos son sintéticos: no hay información real de
personas en ningún archivo de este repositorio.

---

*Este historial de commits fue reordenado para portafolio a partir del desarrollo original
(hecho en 2-3 días intensivos con Claude Code): mismo contenido y autoría, en una secuencia más
legible que la del desarrollo real.*
