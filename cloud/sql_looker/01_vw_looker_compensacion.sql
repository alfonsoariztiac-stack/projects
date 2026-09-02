-- employee_360 tiene grano persona x mes (18 filas por persona). sueldo_base y
-- compa_ratio son una foto constante repetida cada mes: sumarlos sin filtrar
-- en Looker Studio los multiplica por 18. Esta vista fija el grano a "una fila
-- por persona activa, último periodo" para que cualquier gráfico de Looker
-- (tabla, scatter, barras) agregue bien por defecto sin campos calculados.
CREATE OR REPLACE VIEW `buk-people-alertas.people_analytics.vw_looker_compensacion` AS
SELECT
  employee_id,
  periodo,
  area,
  cargo,
  job_family,
  job_level,
  etiqueta_nivel,
  pais_contrato,
  genero,
  tramo_edad,
  tramo_antiguedad,
  categoria_vigente,
  score_vigente,
  moneda,
  sueldo_base,
  banda_min,
  banda_med,
  banda_max,
  compa_ratio,
  bajo_banda,
  meses_desde_ultimo_ajuste
FROM `buk-people-alertas.people_analytics.employee_360`
WHERE activo_en_el_mes
  AND periodo = (SELECT MAX(periodo) FROM `buk-people-alertas.people_analytics.employee_360`);
