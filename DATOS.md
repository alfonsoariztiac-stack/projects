# El ambiente de datos

Guía del universo sintético del caso Buk: qué tablas existen, de dónde sale cada
valor y con qué script se pobló.

> Autogenerado por `src/catalogo.py` el 2026-08-31 18:42. No editar a mano.
> Corte del análisis: **2026-08-31** · ventana: **18 meses** · semilla: **20260902**.

## Ninguno de estos datos es real

Todo lo que hay aquí es sintético. No hay datos de Buk ni de ninguna persona
real: nombres, sueldos, evaluaciones y notas se generan con `numpy` y `faker` a
partir de una semilla fija. La escala imita la dotación propia de Buk (~2.000
bukers), **no** los +2 millones de colaboradores que usan su plataforma — esos
son usuarios finales de sus clientes, otra escala y otro problema.

## Dónde estás parado

| | |
|---|---|
| Motor | **DuckDB** 1.5.5 (archivo único, sin servidor) |
| Archivo | `data/out/buk.duckdb` |
| Dialecto | SQL escrito en el subconjunto común con **BigQuery**, sin capa de traducción |
| Export | `data/out/employee_360.parquet` |

DuckDB hace aquí de BigQuery. El SQL de `src/sql/` evita a propósito
`DATE_DIFF`, `DATE_TRUNC` y `SAFE_CAST` —las tres tienen firmas distintas en
cada motor— y resuelve toda la aritmética de fechas con el entero `idx_mes`.
Migrar a producción es cambiar el conector y el nombre del dataset; el SQL no se
toca. Lo que se muestra en la presentación es literalmente lo que correría en el
warehouse de Buk.

### Abrir la base

```bash
uv run python -c "
import duckdb
con = duckdb.connect('data/out/buk.duckdb', read_only=True)
print(con.execute('SELECT * FROM employee_360 LIMIT 5').df())
"
```

### Correr el pipeline completo

```bash
uv run python src/generate_data.py   # 7 fuentes sintéticas -> data/raw/
uv run python src/warehouse.py       # ingesta + limpieza + modelo -> data/out/
uv run python src/catalogo.py        # regenera este documento
```

## El flujo, de punta a punta

```
src/generate_data.py                 estructura causal latente -> 7 archivos
        |
        v
data/raw/  (CSV "de BigQuery" + XLSX "de Google Sheets", uno sucio a propósito)
        |
        v
src/contratos.py + src/ingest.py     contratos, limpieza, cuarentena
        |                            -> data/out/reporte_calidad.md
        v
tablas stg_*  en DuckDB
        |
        v
src/sql/01..05                       vistas -> employee_360 (persona x mes)
        |
        v
data/out/employee_360.parquet        la única tabla que leen las reglas
```

Aparte, y **nunca leído por el pipeline**: `data/laboratorio/` guarda la verdad
latente (el perfil de cada persona, su trayectoria, la etiqueta de tono y tema
de cada nota). Está separado a propósito. Si las reglas pudieran mirar el perfil
que generó los datos, el backtest sería una tautología: estaría comprobando que
el generador funciona, no que las reglas sirven.


## Cómo se llega a los valores: la estructura causal latente

Los datos no se sortean columna por columna. Cada persona recibe un **perfil
latente** que gobierna una trayectoria mensual de *engagement*, y de esa
trayectoria se derivan todos los observables: productividad, CSAT, días sin
vacaciones, cursos, tono de las notas de bitácora, evaluaciones y la propia
probabilidad de salir. Por eso las señales se mueven juntas, como en la realidad,
en vez de ser cinco columnas independientes que por casualidad se cruzan.

### Los cinco perfiles

| Perfil | Peso | Qué le pasa | Cómo se ve en los datos |
|---|---|---|---|
| `estable` | 68% | Nada. Ruido en torno a su nivel | Todas las señales planas |
| `deterioro` | 12% | Desgaste progresivo | Productividad se desploma, sueldo **normal**, muchos días sin vacaciones |
| `estrella_subpagada` | 9% | Buen desempeño mal pagado | Compa-ratio ~0.85, desempeño **sobre** el promedio |
| `bajo_desempeno` | 5% | No alcanza lo esperado | Score bajo desde el inicio, poca formación |
| `nuevo_dificil` | 6% | Onboarding fallido | Solo aplica con antigüedad <400 días |

### La trayectoria

```
engagement(mes) = eng_base + eng_pendiente x avance
   avance = 0                 lejos del ancla (todavía en su nivel base)
   avance = declive_meses     en el ancla (el fondo)
```

El **ancla** es el mes de salida de la persona; para quien sigue activo, el
corte del análisis más una dispersión de hasta 6 meses (parte de la gente en
riesgo está a mitad de camino, no toda en el fondo). `declive_meses` varía entre
6 y 15 por persona: si todos cayeran en el mismo plazo, "detectado con 60 días
de antelación" sería una constante del generador y no una propiedad de las
reglas.

### Derivación de cada observable

| Observable | Fórmula | Nota |
|---|---|---|
| Productividad | `62 + 48·eng + intercepto_persona + N(0, 2.6)` | El intercepto (σ=6.0) es **persistente por persona** |
| CSAT | `2.55 + 2.30·eng + intercepto_csat + N(0, 0.16)` | Solo familias de cara al cliente |
| NPS | `-45 + 135·eng + 45·intercepto_csat + N(0, 7)` | Idem |
| Días sin vacaciones | Acumula +30/mes; se resetea con prob. `0.045 + 0.14·eng` | Quien está desganado toma **menos** vacaciones |
| Nota de desempeño | `clip(1.72 + 2.18·eng + N(0, 0.20), 1, 4)` | Escala 1–4 real de Buk |
| Compa-ratio | `N(0.97 + antigüedad·0.017 + 0.19·(eng_base − 0.745), 0.085)` | La **inclinación por mérito** implementa el lineamiento *Mérito y Desempeño* de Buk |
| Cursos | `Poisson((0.45 + 2.8·eng) · meses_observados / 12)` | **Tasa** por tiempo, más un pulso de onboarding |
| Tono de bitácora | Umbrales sobre `eng` | Temas sorteados del repertorio del perfil |
| Salida | Propensidad por perfil: `estable` 1.0, `deterioro` 4.5, `estrella` 4.0 | 650 salidas en 24 meses (~12%/año) |

### Tres errores de acoplamiento que hubo que corregir

Valen como advertencia sobre generadores sintéticos, porque los tres producían
datos que *parecían* correctos y volvían inútil cualquier regla:

1. **La salida era independiente del perfil.** El estado se marcaba por posición
   en el bucle, antes de que existiera el perfil. `estable` salía 17.2% y
   `deterioro` 19.0%: el 70% de las salidas no tenía ninguna señal previa.
2. **El declive estaba anclado al calendario, no a la salida.** Quien renunció en
   junio 2025 apenas había empezado a caer cuando se fue; su deterioro "ocurría"
   meses después de que ya no estaba. La causa no precedía al efecto, y las
   reglas marcaban al 25% de quienes se iban contra el 28% de quienes se
   quedaban: **lift negativo**.
3. **El ruido mensual superaba a la señal.** Sin intercepto por persona, el
   mismo individuo oscilaba más de un mes a otro (σ=6.5) que lo que se
   distinguía de sus pares (σ≈3.6). Como las reglas leen deltas *dentro* de la
   misma persona, marcaban al 24.9% de la gente sana. Con intercepto persistente
   y ruido mensual de 2.6, ese falso positivo cae a 5.7%.
4. **La compensación no premiaba el mérito.** El compa-ratio salía plano —de
   hecho, levemente invertido— entre bandas de desempeño: quien rendía bajo lo
   esperado quedaba marginalmente más arriba en banda que quien sobresalía. Eso
   contradice de frente el lineamiento *Mérito y Desempeño* del Culture Code.
   Con la inclinación por mérito el orden queda como la política lo produciría:
   Sobresaliente 1.016 · Cumple lo esperado 0.994 · Bajo lo esperado 0.963.

Los cursos tuvieron su propia versión del problema 3: se sorteaba el **total**
por persona y se repartía entre ingreso y salida, así que quien se iba antes
recibía los mismos cursos en menos meses. El dato terminaba diciendo que
formarse mucho predice renunciar. Una métrica acumulada sin denominador de
tiempo casi siempre está midiendo otra cosa.


## Las 7 fuentes crudas (`data/raw/`)

Formatos deliberadamente heterogéneos, como en el ambiente real de Buk: lo que vive en BigQuery llega como CSV, lo que vive en Google Sheets llega como XLSX. Son 7 archivos y 9 contratos porque `gs_desarrollo_bitacora.xlsx` trae dos hojas (cursos y bitácora) y `dim_cargos.csv` es la tabla dimensional de gobernanza, no una fuente operativa.

| Fuente | Archivo | Formato | Leídas | Válidas | Rechazo | Simula |
|---|---|---|---:|---:|---:|---|
| `directorio` | `bq_directorio_personas.csv` | CSV | 2,650 | 2,650 | 0.00% | tabla en BigQuery |
| `compensaciones` | `bq_compensaciones.csv` | CSV | 2,650 | 2,650 | 0.00% | tabla en BigQuery |
| `evaluaciones_90d` | `bq_evaluaciones_90d.csv` | CSV | 2,437 | 2,437 | 0.00% | tabla en BigQuery |
| `evaluaciones_desempeno` | `bq_evaluaciones_desempeno.csv` | CSV | 5,296 | 5,296 | 0.00% | tabla en BigQuery |
| `metricas_operativas` | `gs_metricas_operativas.xlsx` | XLSX | 29,609 | 28,718 | 1.84% | planilla en Google Sheets |
| `cursos` | `gs_desarrollo_bitacora.xlsx` | XLSX | 9,586 | 9,586 | 0.00% | planilla en Google Sheets |
| `bitacora` | `gs_desarrollo_bitacora.xlsx` | XLSX | 9,274 | 9,250 | 0.00% | planilla en Google Sheets |
| `salidas` | `gs_historico_salidas.xlsx` | XLSX | 650 | 650 | 0.00% | planilla en Google Sheets |
| `dim_cargos` | `dim_cargos.csv` | CSV | 1,030 | 1,030 | 0.00% | tabla en BigQuery |

El detalle de cada incidencia está en [`data/out/reporte_calidad.md`](data/out/reporte_calidad.md), y cada fila rechazada en [`data/out/cuarentena/`](data/out/cuarentena/).


## La suciedad inyectada a propósito

`gs_metricas_operativas.xlsx` simula una planilla mantenida a mano durante
meses. No es un adorno: la descripción del cargo pide explícitamente garantizar
la validez de la información *"a través de la limpieza de las bases de datos"*.
Si la fuente llegara perfecta, la capa de calidad del pipeline no se podría
demostrar.

| Suciedad | Cómo se ve | Qué hace la ingesta |
|---|---|---|
| Encabezados escritos por una persona | `ID Colaborador`, `Mes `, `CSAT (1-5)` | Renombra según el contrato |
| Tres formatos de fecha conviviendo | `2026-08`, `ago-2026`, `08/2026` | Normaliza a `YYYY-MM` |
| Nulos escritos a mano | `N/A`, `s/i`, `-` | Los lee como ausencia de dato |
| Decimales con coma (locale es-CL) | `94,4` | Convierte a punto |
| Espacios en la clave de cruce | `" BUK10427"` | Recorta |
| Valores imposibles | productividad `999`, CSAT `0` | 999 rechaza la fila; CSAT 0 anula la celda |
| Filas duplicadas por copiar y pegar | misma persona y mes repetidos | Conserva la primera |

La distinción entre las dos últimas es deliberada: un CSAT imposible no invalida
la productividad de esa misma fila, pero una productividad imposible sí invalida
la fila entera, porque es la métrica que la fila existe para reportar.

Toda fila rechazada se escribe en `data/out/cuarentena/` con su motivo. Nada
desaparece en silencio. Y si una fuente supera el 5% de rechazo, el pipeline se
detiene en vez de producir alertas sobre datos degradados.


## Las tablas del warehouse

| Objeto | Tipo | Filas | Qué es |
|---|---|---:|---|
| `stg_directorio` | tabla | 2,650 | Directorio de personas (tabla BigQuery) |
| `stg_compensaciones` | tabla | 2,650 | Sueldo base y banda del cargo (tabla BigQuery / reporte Looker) |
| `stg_evaluaciones_90d` | tabla | 2,437 | Evaluación inicial de 90 días (tabla BigQuery) |
| `stg_evaluaciones_desempeno` | tabla | 5,296 | Ciclo anual + mid year feedback, escala 1-4 (tabla BigQuery) |
| `stg_metricas_operativas` | tabla | 28,718 | Productividad, CSAT/NPS y vacaciones por mes (Google Sheets) |
| `stg_cursos` | tabla | 9,586 | Cursos finalizados en Buk University (Google Sheets) |
| `stg_bitacora` | tabla | 9,250 | Notas de seguimiento del HRBP (Google Sheets / Docs) |
| `stg_salidas` | tabla | 650 | Histórico de desvinculaciones y entrevistas de salida (Google Sheets) |
| `stg_dim_cargos` | tabla | 1,030 | Tabla dimensional cargo -> familia x nivel x banda. LA pieza de gobernanza. |
| `dim_periodos` | tabla | 18 | Calendario mensual de la ventana. En BigQuery sería una tabla del dataset común. |
| `dim_cargos_v` | vista | 1,030 | Alias de `stg_dim_cargos`. **La pieza de gobernanza**: mapea cargo → familia × nivel × banda. |
| `persona_mes` | vista | 31,954 | Columna vertebral: una fila por persona × mes, con vigencia calculada a ese mes. |
| `operativa_mes` | vista | 31,954 | Ventanas móviles de productividad y CSAT, calculadas sobre el calendario continuo. |
| `desempeno_mes` | vista | 31,954 | Evaluación vigente y anterior en cada mes, con corrección temporal. |
| `desarrollo_escucha_mes` | vista | 31,954 | Formación y bitácora acumuladas; meses desde el último evento. |
| `employee_360` | tabla | 31,954 | **La tabla que leen las reglas.** Grano: persona × mes. |

## Qué script pobló qué

### `src/generate_data.py` — el generador

Corre una vez y escribe los 7 archivos de `data/raw/` más los 2 de
`data/laboratorio/`. El orden importa: primero existe la persona, después su
perfil, después su destino, y recién entonces se derivan los observables.

| Función | Qué produce |
|---|---|
| `construir_poblacion()` | 2.650 personas: id, nombre ficticio, cargo, país, género, nacionalidad, fecha de ingreso. Calibra la demografía a los valores del Culture Code |
| `_asignar_jerarquia()` | `manager_id` de cada persona, respetando que un líder sea de nivel superior y de la misma área |
| `asignar_perfiles()` | El perfil latente, `eng_base`, `eng_pendiente`, `declive_meses` y los interceptos persistentes de productividad y CSAT |
| `marcar_desvinculados()` | Sortea las 650 salidas **con probabilidad proporcional al perfil**. Es la función que corrige el error nº 1 |
| `generar_salidas()` | Fecha, tipo (voluntaria/no voluntaria), motivo y transcripción de entrevista de salida |
| `anclar_trayectorias()` | `idx_ancla`: el mes contra el cual se mide el declive. Corrige el error nº 2 |
| `engagement()` | Evalúa la trayectoria de una persona en un mes dado. Es la función que todas las demás consultan |
| `generar_compensaciones()` | Sueldo base, banda min/med/max por `job_family × job_level × país`, compa-ratio, fecha del último ajuste |
| `generar_eval_90d()` | Evaluación inicial de 90 días, solo para quien ya la cumplió |
| `generar_eval_desempeno()` | Ciclo anual + mid-year de julio, escala 1–4 |
| `generar_metricas_operativas()` | Productividad, CSAT, NPS y días sin vacaciones, mes a mes |
| `ensuciar_metricas()` | **Degrada a propósito** la planilla operativa: las 7 suciedades de la tabla anterior |
| `generar_cursos()` | Cursos de Buk University como tasa por tiempo observado, con pulso de onboarding |
| `generar_bitacora()` | Notas de seguimiento de 80–200 palabras, compuestas por tono y temas del perfil |

### `src/contratos.py` — la frontera

No produce datos: declara qué se espera de cada fuente. Es además una
**allowlist**: una columna que no está declarada no entra al pipeline aunque
venga en el archivo. Por eso `email` no aparece en ninguna parte del módulo —
existe en el origen y nunca cruza. `nombre` sí entra, pero se queda en staging y
no llega a `employee_360`: se une al final, solo para renderizar la alerta a
quien está autorizado a verla.

### `src/ingest.py` — limpieza y cuarentena

| Función | Qué hace |
|---|---|
| `leer()` | Abre CSV o XLSX, renombra encabezados según el contrato, recorta a las columnas declaradas |
| `norm_*()` | Normalizadores por tipo. `norm_periodo()` acepta los tres formatos de fecha que conviven en la planilla |
| `validar()` | Aplica rangos y obligatoriedad. Campo obligatorio fuera de rango → rechaza la fila; campo opcional → anula la celda y conserva la fila |
| `integridad()` | Falla si algún `(cargo, país)` del directorio no existe en `dim_cargos`. **Es el test de gobernanza**: con 325 cambios internos al año, es el que avisa que la tabla dimensional quedó atrás |
| `ingestar()` | Orquesta todo y devuelve tablas limpias + reporte |
| `escribir_reporte()` | `data/out/reporte_calidad.md` y los CSV de `data/out/cuarentena/` |

### `src/warehouse.py` — el modelo

Carga las tablas limpias en DuckDB como `stg_*`, construye `dim_periodos` y
ejecuta los archivos de `src/sql/` **en orden alfabético**:

| Archivo | Objeto | Qué resuelve |
|---|---|---|
| `01_persona_mes.sql` | `persona_mes` | La columna vertebral: cruce persona × calendario, con vigencia calculada a cada mes |
| `02_operativa.sql` | `operativa_mes` | Ventanas móviles de 3 meses sobre el calendario continuo, no sobre las filas de la planilla |
| `03_desempeno.sql` | `desempeno_mes` | Evaluación vigente y anterior **con corrección temporal** |
| `04_desarrollo_escucha.sql` | `desarrollo_escucha_mes` | Acumulados de formación y bitácora; meses desde el último evento |
| `05_employee_360.sql` | `employee_360` | Une todo y agrega las normalizaciones por cohorte de antigüedad |

Corrida completa (generación + ingesta + modelo): **~4 segundos**.

## Corrección temporal: el detalle que hace válido el backtest

`employee_360` para el mes *m* contiene **solo lo que se sabía al cierre de m**.
Suena obvio y casi nunca se cumple: lo natural al escribir el SQL es unir la
última evaluación de cada persona a todas sus filas, y ahí el modelo de marzo
queda sabiendo el resultado de la evaluación de julio.

Con esa fuga, el backtest reporta un recall inflado que se desploma el día que
el sistema corre en producción, porque en producción el futuro no está
disponible. La implementación cuenta cuántas evaluaciones **habían ocurrido** a
cada mes y une por esa posición (`03_desempeno.sql`). Verificado: **0
violaciones** en las 31.835 filas.

La única excepción es `sale_en_3_meses`, que mira al futuro a propósito. Está
aislada y documentada como etiqueta de evaluación, jamás como insumo de una
regla.


## `employee_360` — diccionario completo

**31,954 filas · 2,581 personas · 18 meses** (grano: una fila por persona × mes que estuvo vigente).

Las estadísticas son del último mes de la ventana (`2026-08`, 2,000 activos).

| Columna | Tipo | % nulos | Estadística | Qué es |
|---|---|---:|---|---|
| `employee_id` | VARCHAR | 0% | 2581 valores · top: `BUK10810`, `BUK10913`, `BUK10051` | Identificador del buker. Formato `BUK#####`. Clave de cruce de todas las fuentes. |
| `periodo` | VARCHAR | 0% | 18 valores · top: `2026-08` | Mes calendario `YYYY-MM`. Junto a `employee_id` forma el grano de la tabla. |
| `idx_mes` | BIGINT | 0% | min 24,319 · mediana 24,319 · max 24,319 | El mes como entero (`año*12 + mes - 1`). Toda la aritmética de fechas usa esto para que el SQL corra igual en BigQuery y DuckDB. |
| `area` | VARCHAR | 0% | 4 valores · top: `Comercial`, `Operaciones`, `Tecnología` | Área organizacional. Derivada del cargo vía `dim_cargos`. |
| `cargo` | VARCHAR | 0% | 199 valores · top: `Especialista de Renovaciones`, `Project Manager de Implementación`, `Consultor de Implementación` | Título del cargo. **Ninguna regla lo referencia**: se usa `job_family` × `job_level`. |
| `job_family` | VARCHAR | 0% | 12 valores · top: `Ingeniería`, `Customer Success`, `Ventas` | Familia de cargo (12 valores). Eje de gobernanza: las reglas apuntan aquí, no al título. |
| `job_level` | VARCHAR | 0% | 8 valores · top: `IC2`, `IC3`, `IC1` | Nivel (`IC1`–`IC5`, `M1`–`M3`). El otro eje de gobernanza. |
| `etiqueta_nivel` | VARCHAR | 0% | 8 valores · top: `Analista`, `Semi Senior`, `Aprendiz` | Nombre legible del nivel (Analista, Senior, Líder…). |
| `pais_contrato` | VARCHAR | 0% | 5 valores · top: `CL`, `MX`, `CO` | País del contrato (CL/PE/CO/MX/BR). Define banda salarial, moneda y legislación. Distinto de nacionalidad y de país de residencia. |
| `manager_id` | VARCHAR | 1% | 300 valores · top: `BUK10796`, `BUK11964`, `BUK11993` | `employee_id` del líder. Nulo solo para gerencias (M3). |
| `activo_en_el_mes` | BOOLEAN | 0% | 2 valores · top: `True`, `False` | Si la persona estaba vigente al cierre de ese mes. **No** es el estado de hoy: es el estado de entonces. |
| `antiguedad_meses` | BIGINT | 0% | min 0 · mediana 16 · max 115 | Meses desde el ingreso hasta ese mes. |
| `genero` | VARCHAR | 0% | 3 valores · top: `F`, `M`, `No binario / No informa` | Atributo protegido. Solo auditoría de impacto dispar, nunca condición de regla. |
| `nacionalidad` | VARCHAR | 0% | 25 valores · top: `Chilena`, `Mexicana`, `Colombiana` | Atributo protegido (pilar Diversidad Cultural). Solo auditoría. |
| `edad` | BIGINT | 0% | min 21 · mediana 31 · max 53 | Atributo protegido. Solo auditoría. |
| `tramo_edad` | VARCHAR | 0% | 4 valores · top: `26-35`, `36-45`, `<26` | Tramo etario para el panel de equidad (`<26`, `26-35`, `36-45`, `46+`). |
| `moneda` | VARCHAR | 0% | 5 valores · top: `CLP`, `MXN`, `COP` | Moneda del contrato. Los montos NO están convertidos: comparar sueldos entre países exige la banda local, no un tipo de cambio. |
| `sueldo_base` | DOUBLE | 0% | min 1,700 · mediana 1,370,000 · max 21,600,000 | Sueldo base mensual en moneda local. |
| `banda_min` | DOUBLE | 0% | min 1,700 · mediana 1,080,000 · max 17,200,000 | Piso de la banda del cargo (`job_family` × `job_level` × país). 80% de la mediana. |
| `banda_med` | DOUBLE | 0% | min 2,100 · mediana 1,350,000 · max 21,500,000 | Mediana de la banda. Denominador del compa-ratio. |
| `banda_max` | DOUBLE | 0% | min 2,600 · mediana 1,690,000 · max 26,900,000 | Techo de la banda. 125% de la mediana. |
| `compa_ratio` | DOUBLE | 0% | min 0.70 · mediana 1 · max 1.30 | `sueldo_base / banda_med`. 1.0 = en la mediana de su banda. Bajo 0.85 es la señal de equidad interna. |
| `meses_desde_ultimo_ajuste` | BIGINT | 0% | min 1 · mediana 5 · max 36 | Meses desde el último ajuste de renta. Convierte 'gana poco' en 'gana poco y nadie lo ha revisado'. |
| `bajo_banda` | BOOLEAN | 0% | 2 valores · top: `False`, `True` | Sueldo por debajo del piso de la banda. Más grave que un compa-ratio bajo. |
| `score_vigente` | DOUBLE | 15% | min 2.23 · mediana 3.39 · max 3.98 | Score de la última evaluación **ocurrida al cierre de ese mes**, escala 1–4 de Buk. |
| `categoria_vigente` | VARCHAR | 15% | 3 valores · top: `Cumple lo esperado`, `Sobresaliente`, `Bajo lo esperado` | Bajo lo esperado (<3) · Cumple lo esperado (3–3.4) · Sobresaliente (≥3.5). |
| `score_previo` | DOUBLE | 40% | min 2.22 · mediana 3.42 · max 4 | Score de la evaluación anterior a esa. Permite leer la trayectoria, no la foto. |
| `categoria_previa` | VARCHAR | 40% | 3 valores · top: `Cumple lo esperado`, `Sobresaliente`, `Bajo lo esperado` | Categoría de la evaluación anterior. |
| `delta_desempeno` | DOUBLE | 40% | min -0.69 · mediana 0 · max 0.67 | `score_vigente - score_previo`. La caída es la señal; un nivel bajo sostenido ya lo gestiona el líder por su canal. |
| `meses_desde_evaluacion` | BIGINT | 15% | min 1 · mediana 1 · max 8 | Antigüedad de la evaluación vigente. Un dato viejo pesa menos. |
| `score_90d` | DOUBLE | 6% | min 1.76 · mediana 3.37 · max 4 | Score de la evaluación inicial de 90 días. Nulo hasta que ocurre. |
| `recomendacion_90d` | VARCHAR | 6% | 3 valores · top: `Continuar`, `Continuar con seguimiento`, `No superó el período de prueba` | Continuar · Seguimiento cercano · No superó el período. |
| `productividad_pct` | DOUBLE | 3% | min 57.10 · mediana 97.40 · max 124.90 | Productividad del mes contra la meta del rol (100 = en meta). |
| `prod_prom_3m` | DOUBLE | 1% | min 54.57 · mediana 97.70 · max 124.17 | Promedio móvil de 3 meses. Se calcula sobre el calendario continuo, no sobre las filas de la planilla. |
| `prod_prom_3m_previo` | DOUBLE | 13% | min 57.30 · mediana 98.13 · max 124 | Promedio de los 3 meses anteriores a esos. Es el contrafactual del delta. |
| `prod_delta_3m` | DOUBLE | 13% | min -10.03 · mediana -0.30 · max 8.17 | `prom_3m - prom_3m_previo`. La caída de tendencia, no el nivel. |
| `meses_con_prod_3m` | HUGEINT | 0% | min 0 · mediana 3 · max 3 | Cuántos de los últimos 3 meses traen dato. Una caída calculada sobre un solo mes observado es ruido; las reglas exigen ≥2. |
| `csat_prom_3m` | DOUBLE | 52% | min 2.46 · mediana 4.28 · max 5 | CSAT móvil 3 meses. Solo roles de cara al cliente (~47% de la dotación); nulo en el resto **por no aplicar**, no por falta de dato. |
| `csat_delta_3m` | DOUBLE | 58% | min -0.48 · mediana -0.02 · max 0.48 | Variación del CSAT contra los 3 meses previos. |
| `dias_sin_vacaciones` | BIGINT | 3% | min 0 · mediana 124 · max 730 | Días acumulados sin tomar vacaciones. Con política ilimitada, quien está desganado tiende a tomar *menos*: proxy de desgaste. |
| `cursos_12m` | HUGEINT | 0% | min 0 · mediana 3 · max 11 | Cursos de Buk University finalizados en 12 meses. **Crudo, confundido con antigüedad** — usar el ratio de cohorte. |
| `horas_formacion_12m` | HUGEINT | 0% | min 0 · mediana 18 · max 106 | Horas de formación acumuladas en 12 meses. |
| `notas_6m` | HUGEINT | 0% | min 0 · mediana 2 · max 7 | Registros de bitácora en 6 meses. |
| `notas_del_mes` | BIGINT | 0% | min 0 · mediana 0 · max 7 | Registros de bitácora ese mes. |
| `meses_sin_curso` | BIGINT | 4% | min 0 · mediana 2 · max 17 | Meses desde el último curso. |
| `meses_sin_nota` | BIGINT | 1% | min 0 · mediana 1 · max 17 | Meses desde el último registro de bitácora. Alimenta el bloque *qué no sabemos* de la alerta: es un punto ciego del sistema, no un síntoma del colaborador. |
| `fecha_salida` | TIMESTAMP_S | 95% |  | Fecha de desvinculación. **Solo backtest y auditoría.** Prohibida como insumo de reglas. |
| `tipo_salida` | VARCHAR | 95% | 2 valores · top: `Voluntaria`, `No voluntaria` | Voluntaria / No voluntaria. Solo backtest. |
| `salida_lamentada` | BOOLEAN | 95% | 2 valores · top: `True`, `False` | Salida voluntaria de quien cumplía o superaba lo esperado. Es la métrica que le duele al negocio: no toda salida es un problema a prevenir. Solo backtest. |
| `sale_en_3_meses` | BOOLEAN | 0% | 2 valores · top: `False` | Etiqueta que mira al futuro. **La única columna con fuga temporal deliberada**, aislada aquí para evaluar reglas. Jamás insumo de una regla. |
| `tramo_antiguedad` | VARCHAR | 0% | 4 valores · top: `0-11`, `12-23`, `24-47` | Cohorte de antigüedad (`0-11`, `12-23`, `24-47`, `48+`). Denominador de las comparaciones normalizadas. |
| `ratio_formacion_cohorte` | DOUBLE | 0% | min 0 · mediana 0.92 · max 3.70 | `cursos_12m` dividido por el promedio de su cohorte de antigüedad ese mes. <1 = se forma menos que sus pares de igual antigüedad. |
| `ratio_vacaciones_cohorte` | DOUBLE | 3% | min 0 · mediana 0.74 · max 4.45 | `dias_sin_vacaciones` sobre el promedio de su cohorte. Corrige que alguien con 5 meses no pueda acumular 300 días. |
| `cursos_12m_cohorte` | DOUBLE | 0% | min 2.25 · mediana 2.97 · max 3.26 | Promedio de cursos de la cohorte (el denominador, expuesto para poder auditarlo). |
| `dias_sin_vacaciones_cohorte` | DOUBLE | 0% | min 146.19 · mediana 164.05 · max 191.37 | Promedio de días sin vacaciones de la cohorte. |

## Distribuciones de control (2026-08, activos)

Los valores contra los que se calibró el universo, tomados del Culture Code de Buk.

**Género (Buk declara 54% mujeres)**

| genero | n | % |
|---|---|---|
| F | 1078 | 53.9 |
| M | 880 | 44.0 |
| No binario / No informa | 42 | 2.1 |

**País de contrato (expansión: CL 2017, CO 2019, PE 2020, MX 2022, BR 2025)**

| país | n | % | antigüedad mediana | antigüedad máx. |
|---|---|---|---|---|
| CL | 1120 | 56.0 | 17.0 | 115 |
| MX | 303 | 15.2 | 18.0 | 55 |
| CO | 253 | 12.7 | 18.0 | 91 |
| PE | 190 | 9.5 | 16.0 | 79 |
| BR | 134 | 6.7 | 17.0 | 19 |

La mediana es parecida en todos los países porque Buk creció rápido en todos a la vez: la mayoría de cada cohorte entró hace poco. Lo que codifica la expansión es el **máximo** — 115 meses en Chile (2017) contra 19 en Brasil (2025).

**Desempeño en la escala 1–4 de Buk**

| categoría | n | % | score medio |
|---|---|---|---|
| Cumple lo esperado | 945 | 47.3 | 3.29 |
| Sobresaliente | 614 | 30.7 | 3.64 |
| Sin evaluación aún | 270 | 13.5 | — |
| Bajo lo esperado | 171 | 8.6 | 2.78 |

El 13,5% sin evaluación son quienes aún no completan su primer ciclo. No es un dato faltante: es una persona que todavía no tiene evaluación, y las reglas de desempeño simplemente no aplican sobre ella.

**Nivel de cargo (Buk declara ~200 líderes sobre ~1.800 bukers)**

| nivel | etiqueta | n | % |
|---|---|---|---|
| IC1 | Aprendiz | 301 | 15.1 |
| IC2 | Analista | 548 | 27.4 |
| IC3 | Semi Senior | 521 | 26.1 |
| IC4 | Senior | 297 | 14.9 |
| IC5 | Especialista | 101 | 5.1 |
| M1 | Líder | 147 | 7.4 |
| M2 | Subgerente | 67 | 3.4 |
| M3 | Gerente | 18 | 0.9 |

**Compa-ratio**

| media | mediana | % bajo 0.85 | % bajo el piso de banda |
|---|---|---|---|
| 0.995 | 1.0 | 7.2 | 1.9 |

**Edad y antigüedad (Buk declara edad promedio 31)**

| edad media | antigüedad mediana (meses) | nacionalidades |
|---|---|---|
| 31.0 | 17.0 | 25 |


## `data/laboratorio/` — la verdad latente

Dos archivos que **el pipeline no lee jamás**:

| Archivo | Contenido |
|---|---|
| `_verdad_latente.csv` | Por persona: `perfil_latente`, `eng_base`, `eng_pendiente`, `declive_meses`, `idx_ancla`, interceptos, fecha de salida |
| `_bitacora_etiquetas.csv` | Por nota: el tono y los temas con que fue construida |

Sirven para dos cosas: verificar que el generador produce lo que se pretende, y
—en el caso de las etiquetas de bitácora— medir cuánto acierta el LLM contra una
respuesta conocida.

Están separados por la misma razón por la que un laboratorio no guarda los
reactivos junto a las muestras. Si una regla pudiera leer `perfil_latente`, el
backtest comprobaría que el generador funciona, no que las reglas sirven.

## Honestidad obligatoria sobre el backtest

El backtest funciona **por construcción**: los datos son sintéticos y la señal
fue puesta ahí a propósito. Es el **método de validación**, no evidencia de que
el sistema funcione en la realidad. Decirlo antes de que lo pregunten suma
credibilidad; que lo pregunten, resta.

Dato relacionado: cerca del **44% de las salidas** viene del perfil `estable`,
gente sin ninguna señal previa —una oferta inesperada, una mudanza, un cambio de
vida—. Ese porcentaje es el techo de recall del sistema, y es sano que exista.
Un backtest que detectara el 100% describiría un mundo donde las personas son
predecibles, no un sistema que funciona.
