-- ---------------------------------------------------------------------------
-- 04 · Desarrollo (Buk University) y escucha (bitácora).
--
-- Dos señales que se leen mejor por su AUSENCIA que por su presencia:
--   · dejar de formarse suele preceder al desenganche;
--   · dejar de aparecer en la bitácora significa que nadie está conversando
--     con esa persona — y eso es un punto ciego del sistema, no un síntoma
--     del colaborador. Por eso "meses_sin_nota" alimenta el bloque "qué no
--     sabemos" de la alerta, no el puntaje de riesgo.
--
-- LAST_VALUE(... IGNORE NULLS) sobre la ventana acumulada da "el último mes en
-- que pasó algo" sin necesidad de un self-join por rangos.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW desarrollo_escucha_mes AS
WITH cursos_mes AS (
  SELECT
    employee_id,
    EXTRACT(YEAR FROM fecha_finalizacion) * 12
      + EXTRACT(MONTH FROM fecha_finalizacion) - 1 AS idx_mes,
    COUNT(*) AS n_cursos,
    SUM(horas) AS horas
  FROM stg_cursos
  GROUP BY employee_id, idx_mes
),
notas_mes AS (
  SELECT
    employee_id,
    EXTRACT(YEAR FROM fecha) * 12 + EXTRACT(MONTH FROM fecha) - 1 AS idx_mes,
    COUNT(*) AS n_notas
  FROM stg_bitacora
  GROUP BY employee_id, idx_mes
),
base AS (
  SELECT
    pm.employee_id,
    pm.idx_mes,
    COALESCE(c.n_cursos, 0) AS n_cursos,
    COALESCE(c.horas, 0)    AS horas_curso,
    COALESCE(n.n_notas, 0)  AS n_notas
  FROM persona_mes pm
  LEFT JOIN cursos_mes c ON c.employee_id = pm.employee_id AND c.idx_mes = pm.idx_mes
  LEFT JOIN notas_mes  n ON n.employee_id = pm.employee_id AND n.idx_mes = pm.idx_mes
)
SELECT
  employee_id,
  idx_mes,
  n_notas,
  SUM(n_cursos)    OVER v12 AS cursos_12m,
  SUM(horas_curso) OVER v12 AS horas_formacion_12m,
  SUM(n_notas)     OVER v6  AS notas_6m,
  idx_mes - LAST_VALUE(CASE WHEN n_cursos > 0 THEN idx_mes END IGNORE NULLS)
              OVER acumulada AS meses_sin_curso,
  idx_mes - LAST_VALUE(CASE WHEN n_notas > 0 THEN idx_mes END IGNORE NULLS)
              OVER acumulada AS meses_sin_nota
FROM base
WINDOW
  v12 AS (PARTITION BY employee_id ORDER BY idx_mes ROWS BETWEEN 11 PRECEDING AND CURRENT ROW),
  v6  AS (PARTITION BY employee_id ORDER BY idx_mes ROWS BETWEEN 5 PRECEDING AND CURRENT ROW),
  acumulada AS (PARTITION BY employee_id ORDER BY idx_mes
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW);
