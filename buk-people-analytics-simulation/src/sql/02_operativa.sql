-- ---------------------------------------------------------------------------
-- 02 · Señal operativa: tendencia, no foto.
--
-- Un mes malo de productividad no dice nada; tres meses cayendo contra los tres
-- anteriores sí. Las reglas leen deltas, no niveles, justamente para no castigar
-- a quien simplemente rinde bajo la media de su familia de cargo.
--
-- Las ventanas móviles se calculan sobre persona_mes (que es continuo) y no
-- sobre la planilla de origen (que tiene huecos). Si se calcularan sobre el
-- origen, un mes sin reportar correría la ventana y el promedio de "3 meses"
-- podría abarcar cinco.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW operativa_mes AS
WITH metricas AS (
  SELECT
    employee_id,
    CAST(SUBSTR(periodo, 1, 4) AS INTEGER) * 12
      + CAST(SUBSTR(periodo, 6, 2) AS INTEGER) - 1 AS idx_mes,
    productividad_pct,
    csat,
    nps_proceso,
    dias_sin_vacaciones
  FROM stg_metricas_operativas
),
base AS (
  SELECT
    pm.employee_id,
    pm.idx_mes,
    m.productividad_pct,
    m.csat,
    m.nps_proceso,
    m.dias_sin_vacaciones
  FROM persona_mes pm
  LEFT JOIN metricas m
    ON m.employee_id = pm.employee_id AND m.idx_mes = pm.idx_mes
)
SELECT
  employee_id,
  idx_mes,
  productividad_pct,
  csat,
  nps_proceso,
  dias_sin_vacaciones,
  ROUND(AVG(productividad_pct) OVER v3, 6)                        AS prod_prom_3m,
  ROUND(AVG(productividad_pct) OVER v3_previo, 6)                 AS prod_prom_3m_previo,
  ROUND(AVG(productividad_pct) OVER v3 - AVG(productividad_pct) OVER v3_previo, 6)
                                                                  AS prod_delta_3m,
  ROUND(AVG(csat)              OVER v3, 6)                        AS csat_prom_3m,
  ROUND(AVG(csat)              OVER v3 - AVG(csat) OVER v3_previo, 6)
                                                                  AS csat_delta_3m,
  -- Cuántos de los últimos 3 meses traen dato. Una caída calculada sobre un
  -- solo mes observado no es una caída: es ruido. Las reglas exigen >= 2.
  SUM(CASE WHEN productividad_pct IS NULL THEN 0 ELSE 1 END) OVER v3 AS meses_con_prod_3m
FROM base
WINDOW
  v3 AS (PARTITION BY employee_id ORDER BY idx_mes ROWS BETWEEN 2 PRECEDING AND CURRENT ROW),
  v3_previo AS (PARTITION BY employee_id ORDER BY idx_mes ROWS BETWEEN 5 PRECEDING AND 3 PRECEDING);
