# Guion · `deck/presentacion_final.html`

**Abrir esto en un segundo dispositivo (celular o notebook aparte). Nunca en la pantalla
compartida.** El deck no tiene overlay de notas a propósito: la presentación es online y
cualquier tecla de "notas" mostraría este archivo al entrevistador.

- Deck: `deck/presentacion_final.html` — doble clic, sin red, sin build.
- Teclas: `→`/`←` navegar · `1`–`5` ir directo · `T` cronómetro · `R` reiniciarlo · `?` ayuda.
- Compartir **solo la pestaña del deck**, y presentar en **F11**.
- Presupuesto: **15 minutos**. El cronómetro se pone en ámbar al pasarlos.

| Bloque | min | acumulado |
|---|---|---|
| S1 · encargo y tesis | 1:00 | 1:00 |
| S2 · Eje 1 (se dispara el Job al abrir) | 2:30 | 3:30 |
| **DEMO 1** · fuentes + log + tarjeta | 4:00 | 7:30 |
| S3 · Eje 2 + **DEMO 2** (con edición del Doc en vivo) | 3:30 | 11:00 |
| S4 · Eje 3 | 2:30 | 13:30 |
| S5 · Eje 4 | 1:30 | 15:00 |
| *DEMO 3 (opcional)* | *0:45* | *15:45* |

**DEMO 3 es lo primero que se corta** si el reloj aprieta.

---

## Antes de entrar a la sala

```bash
# 1. Credenciales (interactivo — nunca en la sala)
gcloud auth login
gcloud auth application-default login --no-launch-browser
gcloud auth application-default print-access-token   # debe imprimir un token

# 2. El Scheduler está vivo y agendado
gcloud scheduler jobs describe alertas-mensual-trigger \
  --location=southamerica-east1 --project=buk-people-alertas \
  --format="value(state,schedule,timeZone,scheduleTime)"
#   → ENABLED · 30 8 1 * * · America/Santiago · 2026-10-01T08:30

# 3. Nada bloqueando el pipeline local
ss -ltnp | grep 4213    # debe salir vacío (UI de DuckDB)
ls data/cache/llm/ | wc -l   # la caché poblada: es lo que hace que el paso 2 diga EN CACHÉ

# 4. Los scripts de demo, en seco (verificados hoy, deben correr sin tocar nada)
uv run --project cloud python demo_scrubber.py --doc   # lee el Doc REAL por Drive (~3,4 s)
uv run python demo_scrubber.py                          # el mismo, local y sin red (plan B)
bash cloud/evidencia/demo_citas.sh                      # las citas [PERSONA_1] en BigQuery

# 5. Respaldo del catálogo, por si se hace la DEMO 3
cp src/rules/reglas.yaml /tmp/reglas.bak.yaml
```

**Pestañas abiertas y ordenadas, en este orden** (se cambia de fuente compartida, no se
expone el escritorio):

1. El deck (`presentacion_final.html`, F11) ← **la única que se comparte por defecto**
2. Google Sheet `gs_metricas_operativas`
3. Consola de BigQuery, dataset `people_analytics`, panel de tablas a la vista
4. Google Doc `7. BUK10001 · 2026-03-07 · 1:1 Happiness` — **el que se edita en la DEMO 2**
5. Vista Looker de compensación
6. El Space de Google Chat
7. Terminal, en la raíz del repo

**Aviso sobre el Space:** ya hay **tres tandas de las mismas 2 tarjetas** (corrida de
referencia `6nx8t`, ensayo de hoy `996xm`, y la que se dispare en vivo). Es *a favor* —
prueba que es repetible y determinista— pero hay que decirlo antes de que se vea. Si
prefieres el Space limpio, borra las del ensayo antes de compartir.

---

## S1 · El encargo y la tesis · 0:00 – 1:00

> Gracias por el tiempo. Antes de mostrar nada, quiero decir cuál me parece que es la
> dificultad real del encargo, porque condicionó todo lo demás.
>
> El caso pide **detectar riesgo de desvinculación o baja productividad** y, en la misma
> frase, pide **que los líderes no estigmaticen**. Esas dos cosas están en tensión. Un
> sistema que le dice a un jefe *"esta persona tiene 78% de riesgo de fuga"* cumple la
> primera mitad y rompe la segunda: un número invita a rankear personas.
>
> Así que la unidad de entrega no es un score. Es **una hipótesis con su evidencia, una
> acción sugerida y una fecha de vencimiento**. Se dispara solo cuando dos dimensiones
> independientes dicen lo mismo, llega al Happiness Manager —nunca al líder directo—, trae
> un "Qué no sabemos" obligatorio y expira a los 30 días.
>
> Una aclaración de honestidad: **los datos son sintéticos**, 2.581 personas y 18 meses de
> historia. **El sistema que los procesa, no.** Está desplegado en GCP y agendado: corre
> solo el día 1 de cada mes a las 08:30, y el próximo disparo real es el 1 de octubre.
>
> *(señalar el recorrido)* Cuatro láminas, una por eje, y tres demos sobre el sistema real.
> **De hecho, empiezo por ahí:** voy a adelantar a mano la corrida del 1 de octubre. Tarda
> unos 90 segundos, así que la disparo ahora y volvemos a verla al final de la próxima
> lámina.

---

## S2 · Eje 1 · Fuentes, ETL y orquestación · 1:00 – 3:30

### Paso 0 · disparar, al abrir la lámina (10 s)

Cambiar a la terminal, pegar, volver al deck:

```bash
gcloud scheduler jobs run alertas-mensual-trigger \
  --location=southamerica-east1 --project=buk-people-alertas
```

Retorna al instante y **no imprime nada** — eso es normal, decirlo en voz alta.

> Esto es exactamente lo que va a pasar solo el 1 de octubre a las 08:30. Lo estoy
> adelantando a mano. Volvemos en tres minutos.

**Si diera error de permisos**, plan B sin dramatizarlo (salta el Scheduler, prueba el Job):

```bash
gcloud run jobs execute alertas-mensual \
  --region=southamerica-west1 --project=buk-people-alertas
```

### El guion de la lámina

> Empiezo por las fuentes, porque el enunciado nombra seis y **las seis existen, cada una
> en el sistema donde el caso las pone**. No hay ninguna que yo haya "asumido".
>
> Directorio y evaluaciones son **tablas de BigQuery**: lectura nativa. Las métricas
> operativas viven en un **Google Sheet**, y las leo como **external table sobre Drive** —
> no las bajo a mano ni las copio: BigQuery consulta la planilla. Compensaciones es una
> **vista de Looker sobre BigQuery**: la tabla es la fuente, Looker es la capa de arriba.
> Desarrollo y escucha son Sheets **más Google Docs de verdad**, leídos con la Drive API y
> la Docs API. Y el histórico de salidas es un Sheet que **alimenta el backtest y nunca
> dispara una alerta** — eso es deliberado y lo retomo en el Eje 3.
>
> *(pasar al contrato)* En el medio hay una capa que para mí es la decisión de diseño más
> importante del eje: **el contrato de datos**. Y lo explico como un ETL, porque eso es.
>
> **La E** son las tablas `raw_*`: external tables con esquema explícito, **todo STRING, sin
> autodetect**. A propósito: ahí el dato está *pre-validación*, con comas decimales, tres
> formatos de fecha, ids con espacios, duplicados y huérfanos. Si dejara que BigQuery
> adivine los tipos, el primer valor raro me rompe la carga y no sé por qué.
>
> **La T** es el contrato, y es **declarativo**: clave primaria, columnas obligatorias,
> tipos, rangos y valores válidos por fuente. Tres cosas que quiero decir en voz alta:
>
> - Es una **allowlist**. `email` no está declarado en ninguna parte. Existe en el origen y
>   **nunca cruza la frontera**. No es que lo borre después: es que nunca entra.
> - Lo que no valida va a **cuarentena con su motivo**, no se descarta en silencio. Y si una
>   fuente supera **5% de rechazo, el pipeline se detiene**: prefiero no entregar a entregar
>   sobre datos rotos.
> - El mismo contrato **genera el DDL de BigQuery**. Quien abra el esquema en la consola lee
>   la regla que la fila tuvo que cumplir para estar ahí.
>
> El resultado: **63.182 filas leídas, 62.267 válidas, 98,6%**, y la peor tasa de rechazo es
> **1,84%** contra un corte de 5%.
>
> **La L** son los `stg_*`, cinco modelos SQL, y `employee_360`: una persona, un mes, una
> fila. 31.954 × 55. Y es `CREATE OR REPLACE TABLE`, **no una vista**: la foto del mes se
> congela a propósito, para que alguien editando una planilla tarde **no cambie una alerta
> que ya se envió**.
>
> *(orquestación)* Encima de eso: **Cloud Scheduler dispara un Cloud Run Job**, el Job corre
> cinco fases contra BigQuery y termina posteando a la Chat API. Todo en
> `southamerica-west1`: el dato de personas no sale de Chile.
>
> **Y quiero justificar por qué es un job efímero y no una plataforma-servicio escuchando
> 24/7**, porque es una decisión, no una comodidad.
>
> - **Es un problema de cadencia, no de latencia.** Las ventanas de comparación y el
>   enfriamiento son de tres meses. Correr esto semanalmente no descubre gente nueva:
>   repite a la misma.
> - **Superficie de ataque.** Un servicio tiene un endpoint que escucha, autentica y puede
>   ser alcanzado, sobre datos con PII de 2.581 personas. Un Job **no tiene endpoint**: solo
>   lo dispara el Scheduler, con su propia identidad de service account.
> - **No queda nada vivo.** El contenedor se levanta, corre 59 segundos y muere. Sin estado
>   en memoria, sin caché de PII persistente, sin proceso de larga vida al que engancharse.
> - Y por costo y operación: **descarté n8n**, porque la lógica termina viviendo en un canvas
>   y no en git, y **descarté Composer/Airflow**, que es un scheduler persistente para 12
>   corridas al año. Lo que sí necesito es que el job sea **idempotente**: reprocesar un mes
>   no duplica nada.

**Si alguien pregunta "¿y si necesitan una alerta en el momento?"** → *"Entonces cambia el
problema y cambia la arquitectura: eso es un evento, no una revisión mensual. Lo que no
cambiaría es el contrato ni el catálogo de reglas; cambiaría el disparador."*

---

## DEMO 1 · el flujo entero, disparado a mano · 3:30 – 7:30

### Paso 1 · el recorrido de las fuentes (~2 min, mientras el Job corre)

Cambiar de pestaña compartida en este orden y **nombrar cada una en una frase**:

1. **Sheet `gs_metricas_operativas`** → *"Encabezados humanos: «Productividad %», «CSAT
   (1-5)». Está sucio como está sucio un Sheet de verdad. BigQuery lo lee como external
   table, no lo copio."*
2. **Consola de BigQuery** → *"Acá están las dos capas a la vista: las `raw_*`, que son las
   external tables sobre Drive, y las `stg_*` más `employee_360`, que son el dato ya
   contratado. El ETL no está escondido en ninguna parte."*
3. **Google Doc de bitácora** → *"Esto es una nota de seguimiento real, con nombres. Es la
   fuente del Eje 2, y en la próxima lámina muestro qué le pasa a este texto antes de salir."*
4. **Vista Looker de compensación** → *"Compa-ratio, que es la señal de compensación. La
   tabla vive en BigQuery; Looker es la vista encima."*

Directorio, evaluaciones y salidas se nombran desde la tabla de la lámina — no hace falta
abrir las siete pestañas.

### Paso 2 · el log fresco, comentado (~90 s) — **el corazón de la demo**

```bash
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="alertas-mensual"' \
  --project=buk-people-alertas --freshness=10m --order=asc --limit=300 \
  --format="value(timestamp,textPayload)"
```

Si hubiera dos ejecuciones mezcladas, la variante determinista (pedir el id con
`gcloud run jobs executions list --job=alertas-mensual --region=southamerica-west1 --limit=1`):

```bash
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="alertas-mensual"
   AND labels."run.googleapis.com/execution_name"="<EXEC_ID>"' \
  --project=buk-people-alertas --order=asc --limit=300 \
  --format="value(timestamp,textPayload)"
```

Comentarlo por fases. **El log evidencia los cuatro ejes por sí solo** — decirlo así:

- **`1/5 cargar_bq` → Eje 1.** Las nueve fuentes con `leídas → válidas`. Detenerse en la
  única línea marcada con `!`: `metricas_operativas 29.609 → 28.718 (546 rechazadas, 345
  duplicadas)`.
  > **El contrato no falló: el contrato funcionó.** Esas 546 filas están en cuarentena con
  > su motivo, no descartadas en silencio, y 1,84% está muy debajo del corte de 5%.

  Y la línea de identidad: corre como `pipeline-alertas@…iam.gserviceaccount.com`, **no como
  una persona**.
- **`2/5 correr_sql` → Eje 1.** Los cinco modelos y **100 MiB facturados** por corrida
  completa. *"Esto cuesta centavos al mes."*
- **`3/5 pipeline` → Eje 3.** `catálogo v1.2.0 · 6 reglas · 11 señales · 5 descartadas`, y
  el desglose por canal. *"Ahí se ve el cupo como capacidad y los que quedan en lista de
  seguimiento, que no se esconden."*
- **`4/5 enriquecer_notas` → Eje 2.** `94 notas en ventana · 0 nuevas · 0 llamadas al
  modelo`.
  > Cero llamadas: es incremental por **hash de la nota ya redactada**. Reprocesar un mes no
  > vuelve a mandar el texto a un tercero ni a pagar el token. Y fíjense **dónde** está esta
  > fase: **después** de decidir, no antes.
- **`5/5 enviar_chat` → Eje 4.** Las tarjetas con nombre y regla, `2 con contexto
  cualitativo`, `OK · corrida completa en 59,1 s` y `Container called exit(0)`.

### Paso 3 · la tarjeta que acaba de llegar (~30 s)

Abrir el Space. La tarjeta tiene **hora de hace un minuto**.

> No es una maqueta ni una captura: es el mensaje que le llegaría al Happiness Manager.
> En la última lámina desarmo esta tarjeta decisión por decisión.

**Decir antes de que se vea:** *"Son las mismas dos personas de las corridas anteriores. El
mes es el mismo y el resultado es determinista — eso es exactamente lo que quiero de un
pipeline."*

**Si el disparo falló o el log no llega:** ir a `cloud/evidencia/alertas-mensual-996xm.log`
(o `-6nx8t.log`) y comentarlo **con este mismo guion, sin cambiar una palabra**. Y mostrar
`gcloud scheduler jobs describe …` para probar que está agendado. Las tarjetas de las
corridas anteriores ya están en el Space.

---

## S3 · Eje 2 · IA sobre el texto · 7:30 – 11:00

> El enunciado pregunta cómo usaría IA sobre las notas de bitácora y qué precauciones
> tomaría. Empiezo por la decisión que ordena todo lo demás: **el texto entra como contexto
> de una alerta que ya existe. Nunca la genera.**
>
> *(la cadena de arriba)* La nota sale del Doc, pasa por el **scrubber**, se le saca un
> **sha256 del texto ya redactado**, se busca en caché, recién ahí va al modelo con
> **esquema cerrado y temperatura 0**, y a la vuelta se **valida**, con un reintento y si
> no, `no_procesado`.
>
> **Antes de la llamada.** La allowlist del contrato ya dejó `email` fuera del perímetro, y
> el texto de las entrevistas de salida se queda en staging: **nunca sale crudo hacia un
> tercero**. Después está el scrubber, y es **determinista, no estadístico**: hace match
> contra el directorio real —2.648 nombres completos y 1.902 tokens— más regex de ids
> `BUK#####`, correos, montos y clientes.
>
> El argumento de por qué así: **un extractor de entidades falla en silencio; una lista del
> directorio falla ruidosamente** si está desactualizada. Prefiero el error que se ve.
> Y cada persona distinta se numera `[PERSONA_1]`, `[PERSONA_2]`: se conserva **si la nota
> habla de una o de varias**, no de cuál.
>
> Hay además una **guarda por corrida**: si un solo token concentra más del 20% de las
> redacciones, se detiene con error. Eso nació de un bug real y medido — la partícula
> "del" se estaba redactando 14.104 veces sobre 9.274 notas. Lo arreglé, y **dejé la guarda
> puesta**, que es lo que importa. En producción esto es **Cloud DLP**; esta versión es la
> que se puede auditar leyendo un archivo entero en un minuto.
>
> **En la llamada.** El esquema es **cerrado, con enums**: cuatro sentimientos, doce temas,
> máximo tres temas y tres citas. El prompt prohíbe inferir salud, situación familiar,
> orientación sexual, religión, nacionalidad o intención de renuncia — **y esas categorías
> no existen en el esquema, así que no hay dónde ponerlas**. Es la diferencia entre pedirlo
> y hacerlo imposible.
>
> Sobre residencia del dato: **el adaptador soporta Vertex AI** —es un switch de
> configuración, implementado y probado— **y es lo que va a producción**, porque mantiene el
> dato dentro del perímetro contractual de GCP y sin entrenamiento sobre el input. **La
> corrida que acaban de ver usó la API con clave y la caché local.** La capa es agnóstica al
> proveedor: es una función `procesar_nota()`. Lo que **no** cambiaría al cambiar de modelo
> es el esquema cerrado ni la anonimización previa.
>
> **Después de la llamada.** Cada cita de respaldo tiene que aparecer **textual en la nota
> redactada**. Es detección de alucinación sin un segundo modelo. Y verificar contra el
> original sería un error: dejaría que una cita "válida" reconstruyera un nombre que el
> scrubber ya había quitado. `insuficiente` es una respuesta válida; lo que no valida se
> reintenta una vez y queda `no_procesado` — **nunca se completa con un valor plausible**,
> porque eso no se distingue de una lectura real. Se guarda modelo, versión de prompt,
> timestamp y hash. **Nunca el texto original.**
>
> *(el circuito cerrado)* ¿Y dónde aterriza esto? En una **tabla propia**, `bitacora_llm`, y
> la tarjeta la lee al construirse. Dos consecuencias:
>
> - Corre **después** de `pipeline`, y solo sobre las personas que ya van a recibir tarjeta:
>   **45 personas y 94 notas este mes, en vez de las 9.250 de la bitácora**. Eso es
>   **minimización de datos**, no solo anonimización: el texto de la gente sobre la que no
>   vamos a actuar no sale del perímetro ni siquiera redactado.
> - Y el sentimiento **no existe como columna en `employee_360`**, que es la tabla que las
>   reglas leen. Ninguna regla puede referenciarlo aunque alguien quisiera. **No es una
>   prohibición: es una imposibilidad estructural.**
>
> Por qué me importa tanto: si lo que dices en una conversación de confianza puede volverse
> una señal de riesgo, **dejas de decirlo**. Y en el Eje 4 hay un veto que mide exactamente
> eso.

### DEMO 2 · "el modelo nunca ve un nombre" (~90 s) — sobre el Doc real, en vivo

El script lee el **Google Doc de verdad** por Drive + Docs API (3,4 s medidos). Si editas
el Doc en el navegador y vuelves a correr, cambia la redacción **y cambia el hash**.

1. **Pestaña del Doc** `7. BUK10001 · 2026-03-07 · 1:1 Happiness`, ya abierta:
   *"Esta es la nota, como la escribió el Happiness Manager. Dice un nombre."*
2. **Terminal** — un comando hace el antes, el después y lo que queda guardado:
   ```bash
   uv run --project cloud python demo_scrubber.py --doc
   ```
   Salida verificada hoy:
   - **ANTES:** `…Valora el espacio que le da Daniela para tomar decisiones…`
   - **DESPUÉS:** `…Valora el espacio que le da [PERSONA_1] para tomar decisiones…`
   - **GUARDADO:** `data/cache/llm/6686581e69f4257cb9199b45.json` · `EN CACHÉ` ·
     claves `hash_nota · modelo · version_prompt · procesado_en · texto_scrubbed ·
     sentimiento · temas · senales · citas_respaldo · confianza`

   > *(ANTES/DESPUÉS)* "El nombre salió. La redacción es **determinista**: match contra la
   > lista de nombres del **directorio real**, no un extractor de entidades. Un extractor
   > falla en silencio; una lista falla ruidosamente si está desactualizada."
   >
   > *(GUARDADO)* "En el archivo hay `texto_scrubbed`, **nunca el original**. Y el nombre
   > del archivo **es el hash del texto de abajo**, del ya redactado: la clave de caché no
   > puede filtrar lo que el scrubber quitó."
   >
   > *(`citas_respaldo`)* "El modelo tuvo que respaldar su lectura con texto que aparece
   > **literal** en lo que se le mostró. Es detección de alucinación sin un segundo modelo —
   > y se verifica contra el texto redactado, no contra el original: si no, una cita
   > 'válida' podría reconstruir el nombre que acabamos de sacar."

3. **La edición en vivo** — volver al Doc y pegar al final esta frase (ensayada, ver la
   advertencia de abajo):

   > `Comentó que Cristina Ibarra lo apoyó en el cierre con Andes Retail y que le ofrecieron $1.800.000 en otra empresa; escribirle a c.ibarra@buk.cl.`

   `Ctrl+S` no hace falta: Docs guarda solo. Volver a la terminal y **repetir el mismo
   comando**. Salida verificada:
   ```
   … Comentó que [PERSONA_2] lo apoyó en el cierre con [CLIENTE] y que le
   ofrecieron [MONTO] en otra empresa; escribirle a [CONTACTO].
   estado: SIN CACHÉ — el texto cambió, así que el hash cambió
   ```
   Tres cosas que decir, en este orden:
   > "Acabo de escribir eso hace diez segundos y el pipeline ya lo leyó: **es el Doc de
   > verdad, no una copia**."
   >
   > "Miren la numeración: **`[PERSONA_2]`**, no `[PERSONA_1]`. Se conserva **si la nota
   > habla de una persona o de dos** — que es lo que hace que la frase se entienda — pero no
   > **de cuál**. Y el sueldo y el correo también salieron, esos por regex."
   >
   > "Y el hash cambió, así que **`SIN CACHÉ`**: esta sí sería una llamada nueva al modelo.
   > Con el texto idéntico son cero llamadas. Reprocesar un mes no vuelve a mandar el texto
   > ni a pagar el token."

   **Dejar el Doc como estaba**: deshacer con `Ctrl+Z` antes de cambiar de pestaña.

4. **El cierre, que es lo que hace que la demo valga** — que la redacción sobrevive hasta
   la tarjeta:
   ```bash
   bash cloud/evidencia/demo_citas.sh
   ```
   Salida verificada hoy:
   ```
   BUK11103 2026-08 negativo | hay superposición entre su rol y el de [PERSONA_1], y que eso genera fricción innecesaria
   BUK10119 2026-06 positivo | Valora el espacio que le da [PERSONA_1] para tomar decisiones sin microgestión.
   ```
   > Esas son las citas **guardadas en BigQuery**, y siguen diciendo `[PERSONA_1]`. Y en la
   > tarjeta que llegó al Space *(volver a esa pestaña y apuntar la cita)* dice lo mismo. Es
   > **una sola cadena de punta a punta**, no dos textos distintos.

#### ⚠ Advertencia — el nombre que escribas tiene que estar en el directorio

El scrubber hace match contra `bq_directorio_personas.csv`. Un nombre inventado
**no se redacta**: probado hoy, `Zoraida Wittgenstein` sale intacta. Si improvisas un
nombre en vivo puede quedar sin redactar en pantalla compartida.

- Usa **`Cristina Ibarra`** (verificada) o cualquiera del directorio.
- Clientes válidos: `Andes Retail`, `Grupo Marítimo`, `Constructora Sur`,
  `Clínica Los Robles`, `Transportes Bío`, `Alimentos del Valle`, `Farmacias Vitalis`,
  `Textil Aurora`.
- Montos, correos e ids `BUK#####` son regex: cualquiera funciona.

Y si alguien lo nota o lo pregunta, la respuesta honesta es la mejor que tienes:
> "Correcto, y es exactamente por eso que **la lista sale del directorio vigente y se
> reconstruye en cada corrida**: si alguien no está en el directorio, tampoco está en
> ninguna nota como colaborador. Un nombre externo es un caso distinto, y para eso la
> versión de producción es **Cloud DLP**, no esta lista. Esta es la versión que se puede
> auditar leyendo un archivo entero en un minuto."

#### Plan B si Drive falla o la sesión caducó

Mismo script, origen local, sin red y sin credenciales:
```bash
uv run python demo_scrubber.py
```
Muestra `BUK10317 · 2026-07-13`, con `Textil Aurora` → `[CLIENTE]` y `Cristóbal` →
`[PERSONA_1]`. Se pierde solo la edición en vivo del paso 3.

---

## S4 · Eje 3 · Señales, reglas, canales y gobernanza · 11:00 – 13:30

> El enunciado pregunta qué reglas definiría para riesgo medio o alto, y cómo las
> mantendría si mañana cambia la estructura de cargos. Las tomo en ese orden.
>
> *(la cadena de arriba)* La estructura es: **11 señales → 4 dimensiones → 6 reglas → 3
> canales**. Cada señal tiene su expresión, su umbral, su justificación escrita y **su lift
> medido** contra el histórico de salidas.
>
> Dos cosas de esa cadena que quiero destacar. La primera: hay señales de **contexto** —
> "cumple" y "sobresaliente"— que **nunca alertan a nadie por sí solas**; están para
> delimitar a quién queremos retener. La segunda, y es la garantía dura del motor: **toda
> combinación que satisface una regla cubre al menos dos dimensiones**. Eso se verifica
> estáticamente antes de correr, y se re-verifica sobre el resultado. **Ninguna alerta nace
> de una sola cosa** — que es la protección más simple contra el falso positivo que
> estigmatiza.
>
> *(la tabla)* Estas son las seis. Tres de nivel **alto** y tres de nivel **medio**, y lo
> importante no es la etiqueta sino **qué implica cada nivel en la entrega**:
>
> - **Alto** es un evento reciente confirmado en dos o más dimensiones, o un incumplimiento
>   objetivo de banda. **Interrumpe el día**: llega como tarjeta de Chat.
> - **Medio** es un estado sostenido. **Se revisa en ciclo y nunca interrumpe.**
>
> Y es verificable: **hoy ninguna tarjeta de Chat es de nivel medio.**
>
> *(los canales)* Por eso son tres canales y no uno. La **conversación** es el único que
> notifica, va al Happiness Manager, tiene **cupo de 35 al mes y enfriamiento de 3 meses**.
> El cupo **es capacidad, no estadística**: People Happiness es un equipo de una decena de
> personas, y 35 conversaciones al mes es lo que puede sostener de verdad. Emitimos 28,7 en
> promedio.
>
> Lo que excede el cupo **no se descarta**: queda en lista de seguimiento, contado en el
> reporte, sin notificar — hoy son 109. Que el sistema encuentre más de lo que el equipo
> puede atender **es el argumento para pedir capacidad**; esconderlo sería el peor error que
> podría cometer con este dato.
>
> Los otros dos canales son paneles, sin cupo y sin enfriamiento. Y **`desarrollo` es la
> mitad "baja productividad" del mandato**, con su propia acción —un plan de
> acompañamiento— en vez de forzarla dentro de una conversación de retención, que no le
> corresponde. Y en el YAML está escrito `nunca_recibe: líder directo, cualquier sistema de
> evaluación de desempeño`. No es una política que alguien recuerda: es una línea del
> catálogo.
>
> *(gobernanza)* Sobre mantenerlo. **El YAML *es* la regla**: no hay lógica de alertas
> escondida en ningún `.py`. El motor lee el catálogo, lo valida y **lo compila a SQL**.
> Está en YAML y no en Python porque **quien gobierna estas reglas es de People Happiness,
> no de Data**: tiene que poder leerlas y aprobar un cambio en un comité sin abrir un editor
> de código.
>
> Y a la pregunta puntual —**si mañana cambia la estructura de cargos**: no se toca ninguna
> regla. `cargo` está en la lista de **atributos prohibidos**, con su razón escrita: *el
> título cambia sin gobernanza*. Las reglas miran **job_family × job_level**, y hay una
> tabla dimensional que mapea cargo × país a familia, nivel y banda. **Un cargo nuevo es una
> fila nueva en esa tabla. El catálogo no se entera.**
>
> Los atributos prohibidos, además, **son un test que falla**, no un comentario: si una
> expresión menciona género, nacionalidad, edad, cargo o nombre, el motor aborta. Esos
> atributos **sí** se usan — pero en la auditoría de equidad, para medir impacto dispar.
>
> Y lo último: versión, bitácora con autor y razón, dueño, revisión trimestral, y la
> documentación se **genera desde el YAML**, así que no puede desincronizarse. Con dos
> piezas que me importan: **las cinco señales descartadas están registradas con su lift**
> —si no las escribes, alguien las propone de nuevo en tres meses— y hay una **regla de
> retiro**. En la versión 1.1.2 saqué una regla del canal de alertas porque no ganaba un
> cupo desde febrero. **La gobernanza se demuestra sacando cosas, no agregándolas.**

### DEMO 3 · opcional (~45 s) — la primera que se corta

1. **Antes de la demo**, respaldar el catálogo:
   `cp src/rules/reglas.yaml /tmp/reglas.bak.yaml`
2. Agregar `AND genero = 'Femenino'` al `expr` de la señal `compa_bajo`
   (`src/rules/reglas.yaml:242`).
3. `uv run python src/rules/motor.py` → aborta. Salida verificada hoy:
   ```
   CatalogoInvalido: La señal 'compa_bajo' referencia el atributo prohibido 'genero'.
   Los atributos protegidos se auditan (equidad.py), no se condicionan.
   ```
4. **Revertir**: `cp /tmp/reglas.bak.yaml src/rules/reglas.yaml`.
   `git checkout` **no sirve** — se llevaría el bloque `contexto_cualitativo` de la
   v1.2.0, que aún no está commiteado.

> La prohibición no es un comentario de buena intención en una política: **es un test que
> falla.**

## S5 · Eje 4 · Interfaz, ética y criterio de éxito · 13:30 – 15:00

> Esta es la tarjeta que llegó hace cinco minutos. Cada decisión acá es una decisión de
> diseño, no una elección estética.
>
> Empieza con **"Contexto para tu próxima conversación con…"**, no con "alerta de riesgo
> sobre…". El encabezado fija qué se espera del lector.
>
> **No hay score, ni porcentaje, ni semáforo.** Un número invita a rankear personas; una
> lista de señales invita a preguntar. Cada señal viene con su evidencia y su período de
> corte, para que se pueda discutir.
>
> Después está el **contexto de las conversaciones registradas**, que es donde aterriza el
> Eje 2: tono, dos temas del enum cerrado, y una cita. **Y la cita dice `[PERSONA_1]`** —
> eso no es un descuido, es la prueba visual de que el modelo nunca vio un nombre. Con su
> descargo literal, que sale del catálogo y no de un f-string: *"no contribuyó a generar
> esta alerta y no evalúa a la persona"*.
>
> **"Qué no sabemos" es obligatoria.** Si una regla no declara su punto ciego, no valida y
> no llega a producción. Acá dice que esta persona no es de cara al cliente, así que no hay
> CSAT que contrastar.
>
> Los tres botones: agendar, "ya lo estoy abordando", y **"Descartar — no aplica"**. El
> tercero es deliberado: **descartar tiene que ser tan fácil como agendar**, o el sistema
> deja de recibir la señal que lo corrige. Y son la única fuente de verdad sobre si la
> alerta sirvió — el backtest solo sabe de quién se fue.
>
> Al pie: **expira en 30 días y no forma parte de su expediente.** Y va por Chat y no por
> correo por una razón concreta: **el correo no caduca**. Una tarjeta puede desaparecer del
> panel; un correo reenviado, no.
>
> *(sesgo punitivo)* Contra el sesgo hay cuatro mecanismos, no cuatro buenas intenciones:
> **separación de canales** —el líder nunca recibe—, **allowlist de columnas** proyectables,
> **caducidad** —30 días de vigencia, 180 de retención, fuera del expediente— y **una señal
> que descarté con evidencia**. Esa última la quiero contar: `desempeno_bajo` tenía lift
> **0,48 sobre salida lamentada** y **2,51 sobre cualquier salida**. Es decir: optimizar
> contra "salida" a secas me construía **un detector de bajo desempeño con etiqueta de
> bienestar**. La saqué, y la dejé registrada con su número.
>
> *(criterio de éxito)* Cómo mediría si funciona, en tres horizontes: a **90 días, que se
> use** —al menos 60% de las tarjetas con una acción registrada—; a **6 meses, que acierte**
> —lift sostenido sobre salida lamentada, medido contra la base del período—; y a **12
> meses, que mueva la aguja** —caída de la tasa de salida lamentada en las áreas cubiertas
> contra las no cubiertas.
>
> Pero un criterio de éxito sin condiciones de apagado no sirve. **Tres vetos**, y si uno se
> dispara el sistema se apaga, no se ajusta: **equidad**, si un grupo protegido queda fuera
> de banda sin explicación; **uso punitivo**, si una alerta aparece citada en una evaluación
> o en una desvinculación; y **enfriamiento del canal**, si la bitácora se seca —menos
> notas, más cortas—, porque eso significa que el sistema **cambió la conversación que decía
> proteger**.
>
> Y tres **anti-métricas**, que es lo que explícitamente no vamos a celebrar: **volumen de
> alertas** —el enfriamiento bajó el volumen 62% y costó 0,3 puntos de cobertura, y fue una
> mejora—; **precisión sin cobertura** —alertar a tres personas y acertar las tres no sirve
> para nada—; y **adopción por obligación** —si se usa porque alguien lo exige, dejó de
> medir lo que decía medir.
>
> Eso es el diseño. Está corriendo, está agendado, y el 1 de octubre lo hace solo.

---

## Preguntas difíciles · respuestas cortas

**"¿Qué tan bueno es realmente el modelo?"**
> No es un modelo predictivo, es un motor de reglas — y eso es deliberado, porque tiene que
> ser explicable ante la persona afectada. Medido sobre el histórico: **lift 3,1 sobre
> salida lamentada** contra una base de 4,5%, con **13,8% de cobertura**. La cobertura es
> baja y la conozco: el techo estructural es 59%, porque muchas salidas no dejan rastro en
> los datos duros antes de irse.

**"¿Por qué la cobertura es tan baja?"**
> Porque el sistema **no ve a quien recién llegó**: la mitad de las señales necesitan tres
> meses de historia, y el 61% de las salidas lamentadas está en el primer año. Es el
> hallazgo más incómodo del análisis y lo dejé escrito en vez de esconderlo. Es también el
> proyecto siguiente, no un parche a estas reglas.

**"¿Esto no es vigilancia?"**
> La diferencia está en tres cosas: **quién recibe** (nunca el líder ni evaluación de
> desempeño), **qué se muestra** (señales con evidencia, sin score, con lo que no sabemos), y
> **cuánto dura** (30 días, fuera del expediente). Y el Veto 2 apaga el sistema si aparece
> citado en una decisión de desvinculación.

**"¿Corre hoy en Vertex AI?"**
> El adaptador **soporta Vertex** y es lo que va a producción — es un switch de
> configuración, implementado y probado. **La corrida que mostré usó la API con clave y la
> caché local.** Prefiero decirlo así a decir que ya está en Vertex.

**"¿Cuánto cuesta esto?"**
> 100 MiB facturados de BigQuery por corrida, 12 corridas al año, un contenedor que vive un
> minuto al mes y las llamadas al modelo solo sobre las notas nuevas de la gente que va a
> recibir tarjeta. El costo dominante no es la infraestructura: son las 35 conversaciones al
> mes del equipo de Happiness.

**"¿Y si el Sheet cambia de columnas?"**
> El contrato falla ruidosamente en la carga y la fuente entra en cuarentena; si supera 5%,
> el pipeline se detiene y no se envía nada. Prefiero una corrida que no ocurre a una
> corrida que alerta sobre datos rotos.

---

## Archivos de respaldo

| Qué | Dónde |
|---|---|
| Log de la corrida de ensayo de hoy (5 fases, 59,1 s) | `cloud/evidencia/alertas-mensual-996xm.log` |
| Log de la corrida de referencia anterior | `cloud/evidencia/alertas-mensual-6nx8t.log` |
| Las dos tarjetas renderizadas como HTML | `data/out/alertas_demo/` |
| Catálogo de reglas legible | `REGLAS.md` (generado desde el YAML) |
| Script de la DEMO 2 · scrubber sobre el Doc real (`--doc`) o local | `demo_scrubber.py` |
| Script de la DEMO 2 · citas redactadas en BigQuery | `cloud/evidencia/demo_citas.sh` |
| Deck anterior, más largo, con el detalle de calibración | `deck/presentacion.html` |
