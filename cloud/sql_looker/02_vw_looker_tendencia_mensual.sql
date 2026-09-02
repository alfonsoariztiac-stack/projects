-- Contraparte de 01: aquí sí se usan los 18 meses, pero pre-agregados por
-- periodo x area con AVG (no SUM), porque el default de Looker Studio sobre un
-- campo numérico crudo es SUM y produciría el mismo error de escala.
CREATE OR REPLACE VIEW `buk-people-alertas.people_analytics.vw_looker_tendencia_mensual` AS
SELECT
  periodo,
  idx_mes,
  area,
  AVG(prod_prom_3m)   AS productividad_prom,
  AVG(csat_prom_3m)   AS csat_prom,
  AVG(score_vigente)  AS desempeno_prom,
  COUNT(*)            AS dotacion
FROM `buk-people-alertas.people_analytics.employee_360`
WHERE activo_en_el_mes
GROUP BY periodo, idx_mes, area;
