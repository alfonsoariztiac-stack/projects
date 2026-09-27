-- ---------------------------------------------------------------------------
-- 01 · Columna vertebral: una fila por persona x mes, con corrección temporal.
--
-- "Point-in-time correctness": la fila de marzo 2026 solo puede contener lo que
-- se sabía al cierre de marzo 2026. Si el modelo de datos deja filtrar una
-- evaluación de julio hacia atrás, el backtest da un recall precioso y falso.
-- Es el error más caro de este tipo de sistema y hay que cerrarlo en el modelo,
-- no en el análisis.
--
-- Toda la aritmética de fechas usa idx_mes = anio*12 + mes - 1 (entero) en vez
-- de DATE_DIFF/DATE_TRUNC. No es capricho: esas dos funciones tienen firmas
-- distintas en BigQuery y en DuckDB, y así este SQL corre literalmente igual
-- en ambos, sin capa de traducción.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW persona_mes AS
WITH persona AS (
  SELECT
    d.employee_id,
    d.area,
    d.cargo,
    d.job_family,
    d.job_level,
    d.pais_contrato,
    d.manager_id,
    d.estado,
    -- Atributos protegidos: viajan para poder AUDITAR impacto dispar.
    -- Ninguna regla de negocio puede leerlos. Ver fairness.py.
    d.genero,
    d.nacionalidad,
    d.fecha_nacimiento,
    d.fecha_ingreso,
    EXTRACT(YEAR FROM d.fecha_ingreso) * 12 + EXTRACT(MONTH FROM d.fecha_ingreso) - 1 AS idx_ingreso,
    s.fecha_salida,
    CASE WHEN s.fecha_salida IS NOT NULL
         THEN EXTRACT(YEAR FROM s.fecha_salida) * 12 + EXTRACT(MONTH FROM s.fecha_salida) - 1
    END AS idx_salida,
    s.tipo_salida,
    s.salida_lamentada
  FROM stg_directorio d
  LEFT JOIN stg_salidas s USING (employee_id)
)
SELECT
  p.employee_id,
  c.periodo,
  c.idx_mes,
  p.area, p.cargo, p.job_family, p.job_level, p.pais_contrato, p.manager_id,
  p.genero, p.nacionalidad,
  p.fecha_ingreso, p.fecha_salida, p.tipo_salida, p.salida_lamentada,
  c.idx_mes - p.idx_ingreso                                   AS antiguedad_meses,
  EXTRACT(YEAR FROM c.fin_mes) - EXTRACT(YEAR FROM p.fecha_nacimiento) AS edad,
  -- Vigencia al cierre de ese mes, no a hoy.
  CASE WHEN p.idx_salida IS NULL OR p.idx_salida > c.idx_mes
       THEN TRUE ELSE FALSE END                               AS activo_en_el_mes,
  -- Marca del backtest: ¿esta persona se fue dentro de los 3 meses siguientes?
  -- Es la única columna que mira hacia adelante y por eso vive aislada aquí:
  -- se usa para evaluar reglas, jamás como insumo de una regla.
  CASE WHEN p.idx_salida IS NOT NULL
        AND p.idx_salida > c.idx_mes
        AND p.idx_salida <= c.idx_mes + 3
       THEN TRUE ELSE FALSE END                               AS sale_en_3_meses
FROM persona p
CROSS JOIN dim_periodos c
WHERE p.idx_ingreso <= c.idx_mes
  AND (p.idx_salida IS NULL OR p.idx_salida >= c.idx_mes);
