-- ---------------------------------------------------------------------------
-- 05 · employee_360 — la tabla que leen las reglas. Grano: persona x mes.
--
-- Un solo lugar del que sale toda alerta. Si mañana alguien pregunta "¿de dónde
-- salió este número?", la respuesta es una fila de esta tabla y las vistas que
-- la componen, no la planilla de alguien.
--
-- SUPUESTO DECLARADO (compensaciones): el origen es una foto al día de hoy, sin
-- historia. Aquí se mantiene constante a lo largo de la ventana. En producción
-- esta tabla debe ser SCD-2 (`vigente_desde` / `vigente_hasta`); mientras no lo
-- sea, el backtest sobrestima levemente las señales de compensación, porque
-- aplica hacia atrás un compa-ratio que quizá no era el de entonces.
-- Se declara en vez de disimularse.
--
-- Señales normalizadas por cohorte de antigüedad: ver el bloque final. Varias
-- métricas crudas (cursos tomados, días sin vacaciones) codifican antigüedad
-- antes que conducta, y una regla escrita sobre ellas mediría qué tan nuevo es
-- alguien disfrazado de analítica.
--
-- La banda se resuelve contra dim_cargos por job_family x job_level x país, no
-- contra el título del cargo. Cuando cambie la estructura de cargos, cambia una
-- tabla dimensional y ninguna regla.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE TABLE employee_360 AS
WITH base AS (
SELECT
  -- Identidad y segmentación
  pm.employee_id,
  pm.periodo,
  pm.idx_mes,
  pm.area,
  pm.cargo,
  pm.job_family,
  pm.job_level,
  dc.etiqueta_nivel,
  pm.pais_contrato,
  pm.manager_id,
  pm.activo_en_el_mes,
  pm.antiguedad_meses,

  -- Atributos protegidos: solo para auditar impacto dispar (fairness.py).
  -- Ninguna condición de rules.yaml puede referenciarlos.
  pm.genero,
  pm.nacionalidad,
  pm.edad,
  CASE WHEN pm.edad < 26 THEN '<26'
       WHEN pm.edad < 36 THEN '26-35'
       WHEN pm.edad < 46 THEN '36-45'
       ELSE '46+' END                                    AS tramo_edad,

  -- Compensación (vocabulario de los lineamientos de Buk)
  co.moneda,
  co.sueldo_base,
  dc.banda_min, dc.banda_med, dc.banda_max,
  co.compa_ratio,
  co.meses_desde_ultimo_ajuste,
  CASE WHEN co.sueldo_base < dc.banda_min THEN TRUE ELSE FALSE END AS bajo_banda,

  -- Desempeño (escala 1-4), vigente a ese mes
  de.score_vigente,
  de.categoria_vigente,
  de.score_previo,
  de.categoria_previa,
  de.delta_desempeno,
  de.meses_desde_evaluacion,
  de.score_90d,
  de.recomendacion_90d,

  -- Operativa
  op.productividad_pct,
  op.prod_prom_3m,
  op.prod_prom_3m_previo,
  op.prod_delta_3m,
  op.meses_con_prod_3m,
  op.csat_prom_3m,
  op.csat_delta_3m,
  op.dias_sin_vacaciones,

  -- Desarrollo y escucha
  ds.cursos_12m,
  ds.horas_formacion_12m,
  ds.notas_6m,
  ds.n_notas                                             AS notas_del_mes,
  ds.meses_sin_curso,
  ds.meses_sin_nota,

  -- Solo para backtest y auditoría. Prohibido usarlas como insumo de reglas.
  pm.fecha_salida,
  pm.tipo_salida,
  pm.salida_lamentada,
  pm.sale_en_3_meses
FROM persona_mes pm
LEFT JOIN stg_compensaciones co ON co.employee_id = pm.employee_id
LEFT JOIN dim_cargos_v dc
       ON dc.cargo = pm.cargo AND dc.pais_contrato = pm.pais_contrato
LEFT JOIN desempeno_mes de
       ON de.employee_id = pm.employee_id AND de.idx_mes = pm.idx_mes
LEFT JOIN operativa_mes op
       ON op.employee_id = pm.employee_id AND op.idx_mes = pm.idx_mes
LEFT JOIN desarrollo_escucha_mes ds
       ON ds.employee_id = pm.employee_id AND ds.idx_mes = pm.idx_mes
)
SELECT
  base.*,
  CASE WHEN antiguedad_meses < 12 THEN '0-11'
       WHEN antiguedad_meses < 24 THEN '12-23'
       WHEN antiguedad_meses < 48 THEN '24-47'
       ELSE '48+' END AS tramo_antiguedad,

  -- Comparación contra la cohorte: misma antigüedad, mismo mes.
  --
  -- Sin esto, "lleva 4 meses sin tomar un curso" parece una señal de
  -- desenganche cuando en realidad describe a alguien con tres años en la
  -- empresa que ya hizo su formación de onboarding. En estos datos la métrica
  -- cruda está INVERTIDA respecto de la intuición: quienes salen llevan MENOS
  -- meses sin curso que quienes se quedan, simplemente porque son más nuevos.
  --
  -- Lo mismo con días sin vacaciones: alguien con 5 meses en Buk no puede
  -- acumular 300 días. Comparar contra su cohorte convierte una variable que
  -- medía antigüedad en una que mide desviación respecto de sus pares.
  cursos_12m / NULLIF(AVG(cursos_12m) OVER cohorte, 0)                 AS ratio_formacion_cohorte,
  dias_sin_vacaciones / NULLIF(AVG(dias_sin_vacaciones) OVER cohorte, 0) AS ratio_vacaciones_cohorte,
  AVG(cursos_12m) OVER cohorte                                         AS cursos_12m_cohorte,
  AVG(dias_sin_vacaciones) OVER cohorte                                AS dias_sin_vacaciones_cohorte
FROM base
WINDOW cohorte AS (
  PARTITION BY periodo,
               CASE WHEN antiguedad_meses < 12 THEN '0-11'
                    WHEN antiguedad_meses < 24 THEN '12-23'
                    WHEN antiguedad_meses < 48 THEN '24-47'
                    ELSE '48+' END
);
