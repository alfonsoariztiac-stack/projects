# `cloud/` — el mismo pipeline, contra Google Workspace

Proyecto `uv` **independiente** (su propio `pyproject.toml` y su propio `.venv`).
Nada de aquí toca `data/out/`, ni `src/`, ni el `pyproject.toml` de la raíz: la
demo local sigue siendo la fuente de verdad y no puede romperse desde acá.

| | |
|---|---|
| Proyecto GCP | `buk-people-alertas` |
| Dataset | `people_analytics` |
| Región | `southamerica-west1` (Santiago) — el dato de personas no sale de Chile |
| Identidad por defecto | ADC del usuario, scope `cloud-platform`. **Sin Drive** |
| Identidad con `--impersonar` | `pipeline-alertas@…`, impersonada, **sin key JSON en disco** |

```bash
uv run --project cloud python cloud/tablas_externas.py  # raw_* sobre las 3 Sheets (F2)
uv run --project cloud python cloud/cargar_bq.py         # fuentes → stg_* (Sheets + CSV)
uv run --project cloud python cloud/correr_sql.py        # src/sql/*.sql tal cual
uv run --project cloud python cloud/verificar.py         # ¿coincide con la corrida local?
```

`tablas_externas.py` solo hace falta correrlo una vez (o cuando cambie el ID de
una Sheet); `cargar_bq.py` lee `raw_*` en cada corrida, así que ve cualquier
edición hecha después.

## F1 — resultado

`employee_360` en BigQuery contra `data/out/employee_360.parquet`:

```
employee_360 · 31.954 filas × 55 columnas · DuckDB (Parquet local) contra BigQuery
   Sin diferencias en ninguna columna.
PASA · 0 celdas distintas entre los dos motores
```

Son **1.757.470 celdas comparadas una por una**, no un `COUNT(*)`. Dos motores
pueden coincidir en el conteo y discrepar en cada promedio móvil; ese es
justamente el error que no se ve.

Estado del dataset: 10 tablas (62.285 filas) + 5 vistas + `employee_360`.

## F2 — las 3 planillas, vivas en el warehouse

**Estado: completa y verificada el 2026-09-01.** La barra de F1 se re-verificó
al terminar F2 y **sigue en 0 celdas distintas** — la migración a Sheets no
cambió un solo número.

### La decisión de nombres: `raw_*` + `stg_*`, no solo `stg_*`

El plan original decía "las external tables se llaman `stg_*`". Se descartó
en la conversación con Alfonso, por dos razones concretas verificadas en el
código antes de escribir una línea:

1. `stg_*` no es la planilla — es lo que pasó el contrato de `src/ingest.py`.
   `stg_metricas_operativas` tiene 28.718 filas; la planilla tiene 29.609. En
   el camino se rechazan 546 filas y se eliminan 345 duplicados. Una external
   table cruda sobre el Sheet es dato *pre-validación*.
2. Los headers del Sheet son texto libre en español ("ID Colaborador",
   "Mes ", "Productividad %", "CSAT (1-5)") — no son identificadores válidos
   sin backticks incómodos en cada query.

Se optó por dos capas, cada una con un rol que se ve en la consola:

- **`raw_metricas_operativas` / `raw_salidas` / `raw_cursos` / `raw_bitacora`**
  — external tables, esquema **explícito** (todo `STRING`, sin autodetect) en
  `cloud/tablas_externas.py`. Los nombres de columna son el vocabulario final
  del contrato (`employee_id`, `periodo`, `csat`...), decidido con Alfonso:
  lo "crudo" de esta capa está en los *valores* (comas decimales, 3 formatos
  de fecha, ids con espacios, duplicados, huérfanos), no en el nombre de
  columna, que de todas formas nunca se lee del archivo — el esquema explícito
  es posicional, no por header.
- **`stg_*`** — sin cambios de nombre ni de forma respecto a F1. Lo que cambia
  es el origen: para las 4 fuentes de Sheets, `cargar_bq.py` ya no abre el
  XLSX de `data/raw/`, consulta `raw_*` en BigQuery.

Esto hace literal la frase de la sala: `SELECT * FROM raw_metricas_operativas`
muestra la edición al instante, y el contrato corre **visiblemente** entre la
planilla y la alerta — no es una promesa, es un paso que se ve en pantalla
(las líneas `! metricas_operativas 29,609 -> 28,718 filas (546 rechazadas...)`
que imprime `cargar_bq.py`).

### Cómo se conecta `cargar_bq.py` sin tocar `ingest.py`

`ingest.ingestar()` no soporta cambiar el origen de una fuente sola, así que
`cargar_bq.py` parcha en caliente (mismo patrón que ya usaba con
`ingest.CUARENTENA`): reemplaza `ingest.leer` por un híbrido que, para las 4
fuentes de Sheets, hace `SELECT * FROM raw_*` en vez de `pd.read_excel()`, y
deja las 5 fuentes CSV intactas. `ingest.validar()` corre igual para las dos:
la calidad de dato no se reimplementa ni se bifurca.

Detalle de identidad: leer `raw_*` **siempre** exige la SA impersonada con
Drive (`config.cliente(impersonar=True, con_drive=True)`), sin importar si
`cargar_bq.py` se invoca con `--impersonar` o no — ese flag solo controla con
qué identidad se escribe el resultado a BigQuery. La credencial personal de
Alfonso nunca lee una Sheet, en ningún camino de código.

### El permiso que faltó y no es Drive

El riesgo declarado del plan (acceso a Drive desde BigQuery) **no se
materializó** — la SA leyó las 4 Sheets a la primera, apenas Alfonso compartió
la carpeta. Lo que sí faltó es otro permiso, sin relación con Drive:
`to_dataframe()` intenta usar la BigQuery Storage API por defecto, que exige
`bigquery.readSessionUser` — la SA no lo tiene (solo `dataEditor` +
`jobUser`). Se resolvió con `create_bqstorage_client=False` en las dos lecturas
que corren como la SA (`tablas_externas.py` y el híbrido de `cargar_bq.py`):
son miles de filas, no millones, y no vale la pena pedir un permiso IAM
adicional por una lectura de este tamaño.

### `raw_*` en el inventario muestra 0 filas — no es un bug

`verificar.py` lista `raw_*` con `0 filas` en el inventario del dataset.
BigQuery no mantiene `row_count` en `INFORMATION_SCHEMA`/`__TABLES__` para
external tables — el conteo real solo sale de un `SELECT COUNT(*)` real
(que sí funciona: son las cifras que imprime `tablas_externas.py`, ej.
`raw_metricas_operativas · 29.609 filas`).

### El guion de demo, cronometrado y ensayado con una edición real

Se ensayó en vivo (2026-09-01): Alfonso cambió `BUK10012`, período `2026-05`,
`productividad_pct` de `74` a `55` en `gs_metricas_operativas`, y se revirtió
al terminar. Dos tiempos, no uno — el plan preguntaba cuál mostrar y la
respuesta es **los dos**, porque prueban cosas distintas:

1. **Instantáneo, sin correr nada.** Apenas Alfonso guarda el cambio en el
   navegador, `SELECT productividad_pct FROM raw_metricas_operativas WHERE
   employee_id = 'BUK10012' AND periodo = '2026-05'` ya devuelve `55` — 0
   segundos de espera, prueba que la conexión es viva.
2. **~53 segundos, con el pipeline a la vista.** `cargar_bq.py` (~45 s: 9
   jobs de carga a BigQuery, la mayoría overhead de red por job, no de
   cómputo) → `correr_sql.py` (~8 s) → el mismo `employee_id`/`periodo` en
   `employee_360` pasa de `74.0` a `55.0`. Este es el tiempo que se ve en
   pantalla mientras se explica qué está pasando: la SA leyendo la Sheet, el
   contrato validando, `stg_metricas_operativas` regenerándose.

**Guion recomendado para la sala:** abrir con (1) — "edito la celda, consulto,
ya está" — y encadenar a (2) mientras se explica en voz alta el paso del
contrato, sin quedarse en silencio 53 segundos. No mostrar solo (1): sin (2)
no queda claro que la alerta también cambia, que es el punto del caso.

**Detalle que no está en el plan y vale la pena decir en la sala:** las vistas
intermedias (`persona_mes`, `operativa_mes`, …) están un escalón más cerca de
`stg_*`, no de `raw_*` — tampoco ven la edición hasta que corre `cargar_bq.py`.
`employee_360` es `CREATE OR REPLACE TABLE`, no vista: nunca se actualiza solo.
Es una decisión de diseño real (congelar la foto del mes, no dejar que una
edición tardía altere una alerta ya enviada) y es exactamente el argumento que
el plan ya anticipaba para el snapshot de F6.

### Archivos que agrega F2

| | |
|---|---|
| `tablas_externas.py` | crea (o reemplaza) `raw_*`: 4 external tables, esquema explícito, sobre las 3 Sheets |

## F3 — el motor de reglas contra BigQuery

**Estado: completa y verificada el 2026-09-01.** `cloud/adaptador.py` expone
`ConexionBQ`/`ResultadoBQ` — el dialecto mínimo que `motor.ejecutar()` le pide
a una conexión (`.execute(sql).df()`, nada más: se comprobó con `grep` que
nada de lo que migra usa `.fetchone()`). `cloud/pipeline.py` es el equivalente
de `motor.main()` contra BigQuery, sin tocar `src/rules/motor.py` ni una
línea. `employee_360` se referencia sin calificar en el texto —
`QueryJobConfig(default_dataset=...)` alcanza porque `compilar(cat)` genera un
`SELECT` plano, no una vista (el problema de F1 con `CREATE VIEW` no aplica
acá) — así que el SQL que llega a BigQuery es carácter por carácter el mismo
que `data/out/alertas.sql`. La tabla `alertas` se carga con
`autodetect=True`: no hay un `CONTRATOS["alertas"]` del cual derivar un
esquema a mano (sus columnas las calcula el motor, no vienen de una fuente), y
BigQuery infiere sola hasta el tipo de `senales`/`evidencia` (listas → `STRING
REPEATED`).

`cloud/verificar.py::comparar()` se generalizó para recibir tabla, DataFrame
local y clave como parámetros, en vez de tener `employee_360` fijo — así
verifica `alertas` sin duplicar la función. La clave de `alertas` es
(`employee_id`, `periodo`, `canal`): una persona puede estar en el panel de
compensaciones y alertada en conversación el mismo mes.

### La comparación celda a celda encontró 3 diferencias reales — y las 3 se entendieron, no se ocultaron

La primera corrida de `cloud/pipeline.py` dio 2.065 candidatas contra 2.062 en
local — `employee_360` seguía en 0 diferencias, así que el problema no venía
de arriba. Se aisló reconstruyendo la CTE `evaluadas` del SQL de
`motor.compilar()` y comparándola persona por persona entre los dos motores.
Ninguna de las tres causas es un problema de sintaxis SQL — el subconjunto
común sigue sosteniéndose — son tres formas distintas de no-determinismo
numérico entre dos motores independientes:

1. **Ventanas móviles no asociativas.** `prod_delta_3m` y `csat_delta_3m`
   ([02_operativa.sql](src/sql/02_operativa.sql)) se calculan restando dos
   `AVG() OVER (ROWS BETWEEN ... PRECEDING)`. La suma en punto flotante no es
   asociativa: DuckDB y BigQuery no tienen por qué sumar las filas de una
   ventana en el mismo orden interno. Para una persona/mes concreto,
   `prod_delta_3m` daba `-3.999999999999986` en DuckDB y `-4.0` exacto en
   BigQuery — una diferencia de `1,4e-14`, invisible para la tolerancia de
   comparación de F1 (`1e-9`), pero suficiente para cruzar el umbral
   `<= -4.0` de una señal en un motor y no en el otro. Arreglo: `ROUND(..., 6)`
   en las 5 columnas de esa vista derivadas de `AVG() OVER` — 6 decimales es
   ~6 órdenes de magnitud más preciso que los datos de origen
   (`productividad_pct`, `csat`), así que no cambia ninguna distinción real,
   solo colapsa el ruido por debajo del sexto decimal.
2. **Multiplicación de constantes.** La señal `desgaste_vacaciones`
   (`reglas.yaml`) compara contra `0.7 * antiguedad_meses * 30`. `0.7` no es
   representable de forma exacta en binario; para una fila donde el resultado
   matemático era exactamente `126`, un motor llegaba a `126.0` justo y el
   otro a un número apenas por debajo, cruzando el `>`. Mismo arreglo, mismo
   principio: envolver el lado derecho en `ROUND(..., 6)` en el `expr` de la
   señal — no se tocó el `0.7` ni el criterio de negocio.
3. **`ORDER BY` sin orden total.** `posicion_en_cola` sale de `ROW_NUMBER()
   OVER (PARTITION BY periodo, canal ORDER BY prioridad, compa_ratio)`. Cuando
   dos personas empatan exactamente en ambos campos, el desempate entre ellas
   queda indefinido por el estándar SQL, y cada motor lo resuelve distinto
   (69 filas afectadas, verificado con casos reales de empate exacto). De esas
   69, solo 10 caían en `conversacion` —el único canal con cupo— y ninguna
   cruzaba el corte de 35: con los datos de hoy no cambiaba una sola
   notificación, pero no había garantía de que siguiera así. Arreglo: agregar
   `employee_id` como tercer nivel de `desempate` — no es un criterio de
   negocio nuevo, es el desempate del desempate, y usa un valor que nunca se
   repite dentro de un grupo.

Ninguno de los tres arreglos toca `motor.py` ni cambia el sentido de una
regla. Tras los tres: `cloud/verificar.py` da `PASA · total · 0 celdas
distintas` para `employee_360` y para `alertas`.

**Cifras finales verificadas (candidatas por canal, ambos motores
idénticos):** `compensaciones` 772 · `conversacion` 703 · `desarrollo` 592.
Estas reemplazan las cifras provisionales de la primera corrida local
(773 / 696 / 593, antes de los tres arreglos) — si algo en `deck/` ya citaba
las cifras viejas, hay que actualizarlo.

### Archivos que agrega F3

| | |
|---|---|
| `adaptador.py` | `ConexionBQ`/`ResultadoBQ`: el dialecto mínimo (`.execute(sql).df()`) que `motor.ejecutar()` necesita |
| `pipeline.py` | equivalente de `motor.main()` contra BigQuery; carga `alertas` con `autodetect=True` |

## Qué se probó y qué se rompió

La tesis del proyecto era que `src/sql/` está escrito en el subconjunto común y
migra sin tocarse. **Se sostuvo**, con una excepción que no es de lenguaje.

Construcciones que se auditaron como sospechosas y corren idénticas en los dos
motores: `CAST(... AS INTEGER)`, cláusula `WINDOW` con nombre,
`LAST_VALUE(... IGNORE NULLS)`, ventanas `ROWS BETWEEN … PRECEDING`, `EXTRACT`,
`SUBSTR`, `CROSS JOIN`, `USING`, `tabla.*`. El ajuste que el plan anticipaba
(`INTEGER` → `INT64`) **no hizo falta**: BigQuery lo acepta.

Lo que sí difiere es del motor, no del dialecto:

> **BigQuery no guarda el dataset por defecto dentro de la definición de una
> vista.** Un `CREATE VIEW` cuyo cuerpo diga `FROM dim_periodos` se rechaza
> aunque el job traiga `default_dataset` seteado.

Y hay una trampa: dentro de una sesión con `SET @@dataset_id`, BigQuery **sí
acepta** ese `CREATE VIEW` — y deja una vista que existe y falla al consultarla
desde fuera de la sesión. Se probó y se descartó; un error silencioso es peor
que un error.

La salida es calificar los nombres **al ejecutar**, no editar el archivo:
`dim_periodos` → `` `buk-people-alertas.people_analytics.dim_periodos` ``. La
lista de qué calificar no está escrita a mano —sale de `CONTRATOS` y de los
propios `CREATE OR REPLACE` de los `.sql`— y los comentarios se dejan intactos,
para que quien abra la vista en la consola lea el mismo texto del repositorio.

```bash
uv run --project cloud python cloud/correr_sql.py --mostrar 02_operativa.sql
```

## Lo que no se reimplementó

`cloud/` importa de `src/` en vez de copiar. Si mañana cambia una regla de
calidad, la carga a BigQuery la hereda sin que nadie se acuerde:

- `ingest.ingestar()` → los 9 DataFrames ya validados, con cuarentena aplicada
- `warehouse.tipar()` → los tipos del contrato aplicados al DataFrame
- `warehouse.dim_periodos()` → el calendario de la ventana
- `contratos.CONTRATOS` → **el esquema DDL de BigQuery se deriva de aquí**, no se
  escribe a mano. `requerido: True` viaja como `REQUIRED`, y los rangos y valores
  válidos viajan como descripción de columna: quien abra el esquema en la consola
  ve la regla que la fila tuvo que cumplir para estar ahí.

Único desvío deliberado: `ingest.CUARENTENA` se redirige a `cloud/.cuarentena/`.
Los artefactos de `data/out/` son los validados y los que consume el deck; una
carga a BigQuery no tiene por qué reescribirlos.

## Archivos

| | |
|---|---|
| `config.py` | proyecto, dataset, región, y credencial ADC o impersonada |
| `tablas_externas.py` | crea `raw_*`: 4 external tables, esquema explícito, sobre las 3 Sheets (F2) |
| `cargar_bq.py` | `CONTRATOS` → esquema BigQuery; ingesta híbrida (Sheets + CSV local) → `stg_*` |
| `correr_sql.py` | ejecuta `src/sql/*.sql` sin modificarlos (`--mostrar`, `--dry-run`) |
| `adaptador.py` | `ConexionBQ`/`ResultadoBQ`: el dialecto mínimo que `motor.ejecutar()` necesita (F3) |
| `pipeline.py` | `motor.main()` contra BigQuery; carga `alertas` como tabla nativa (F3) |
| `verificar.py` | inventario del dataset + comparación celda a celda contra el Parquet, para `employee_360` y `alertas` |

`--dry-run` valida sintaxis y estima costo sin cobrar, pero solo sirve **después**
de la primera corrida: un archivo no ve las vistas que crearía el anterior.

## Siguiente

F4 — Google Chat real: verificar que el webhook de `.env` sigue vivo, una
variante en `cloud/` que lee las alertas desde BigQuery en vez de
`alertas.parquet`, y postear las 3 tarjetas al Space real. Ver el plan en
`~/.claude/plans/sobre-lo-que-no-ancient-treehouse.md`.
