-- ---------------------------------------------------------------------------
-- 03 · Desempeño vigente en cada mes, en la escala 1-4 de Buk.
--
-- La evaluación no es un atributo de la persona: es un atributo de la persona
-- EN UN MOMENTO. En marzo, el desempeño vigente es el del ciclo anual anterior;
-- el mid-year de julio todavía no existe. Se resuelve contando cuántas
-- evaluaciones había ocurrido al cierre de cada mes y trayendo esa y la previa.
--
-- Traer la previa importa: la señal fuerte no es "tiene 3.1", es "venía en 3.6
-- y bajó a 3.1". Un nivel bajo sostenido ya lo gestiona el líder por su propio
-- canal; la caída es lo que el Happiness Manager no ve a tiempo.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW desempeno_mes AS
WITH ev AS (
  SELECT
    employee_id,
    EXTRACT(YEAR FROM fecha_evaluacion) * 12
      + EXTRACT(MONTH FROM fecha_evaluacion) - 1 AS idx_mes,
    ciclo, tipo_ciclo, score_final, score_objetivos, score_valores, categoria
  FROM stg_evaluaciones_desempeno
),
ev_rank AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY idx_mes, ciclo) AS rn
  FROM ev
),
ev_por_mes AS (
  SELECT employee_id, idx_mes, COUNT(*) AS n_ev
  FROM ev GROUP BY employee_id, idx_mes
),
acumulado AS (
  SELECT
    pm.employee_id,
    pm.idx_mes,
    SUM(COALESCE(e.n_ev, 0)) OVER (
      PARTITION BY pm.employee_id ORDER BY pm.idx_mes
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS evals_hasta_el_mes
  FROM persona_mes pm
  LEFT JOIN ev_por_mes e
    ON e.employee_id = pm.employee_id AND e.idx_mes = pm.idx_mes
),
noventa AS (
  SELECT
    employee_id,
    EXTRACT(YEAR FROM fecha_evaluacion) * 12
      + EXTRACT(MONTH FROM fecha_evaluacion) - 1 AS idx_mes_90d,
    score_desempeno            AS score_90d,
    score_adaptacion_cultural  AS score_adaptacion_90d,
    recomendacion              AS recomendacion_90d
  FROM stg_evaluaciones_90d
)
SELECT
  a.employee_id,
  a.idx_mes,
  a.evals_hasta_el_mes,
  act.ciclo             AS ciclo_vigente,
  act.tipo_ciclo        AS tipo_ciclo_vigente,
  act.score_final       AS score_vigente,
  act.score_objetivos   AS score_objetivos_vigente,
  act.score_valores     AS score_valores_vigente,
  act.categoria         AS categoria_vigente,
  a.idx_mes - act.idx_mes AS meses_desde_evaluacion,
  prev.score_final      AS score_previo,
  prev.categoria        AS categoria_previa,
  act.score_final - prev.score_final AS delta_desempeno,
  -- La evaluación de 90 días solo es visible una vez ocurrida.
  CASE WHEN n.idx_mes_90d <= a.idx_mes THEN n.score_90d END            AS score_90d,
  CASE WHEN n.idx_mes_90d <= a.idx_mes THEN n.score_adaptacion_90d END AS score_adaptacion_90d,
  CASE WHEN n.idx_mes_90d <= a.idx_mes THEN n.recomendacion_90d END    AS recomendacion_90d
FROM acumulado a
LEFT JOIN ev_rank act
  ON act.employee_id = a.employee_id AND act.rn = a.evals_hasta_el_mes
LEFT JOIN ev_rank prev
  ON prev.employee_id = a.employee_id AND prev.rn = a.evals_hasta_el_mes - 1
LEFT JOIN noventa n
  ON n.employee_id = a.employee_id;
