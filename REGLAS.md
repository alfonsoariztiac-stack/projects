# Catálogo de alertas de retención · v1.1.2

> Generado por `src/rules/documentar.py` el 2026-09-02 10:33.
> No editar a mano: la fuente de verdad es `src/rules/reglas.yaml`.

| | |
|---|---|
| **Versión** | 1.1.2 |
| **Vigente desde** | 2026-09-01 |
| **Dueño** | People Happiness · en conjunto con People Analytics |
| **Ciclo de revisión** | trimestral |
| **Frecuencia de corrida** | mensual |
| **Retención de alertas** | 180 días |

## Qué decide este sistema

Este catálogo cubre las DOS mitades del mandato ("riesgo de desvinculación o baja productividad"), con un canal distinto para cada una porque no son la misma pregunta ni piden la misma acción: (1) Riesgo de SALIDA LAMENTADA —quien cumple o supera lo esperado y renuncia— vía el canal `conversacion`, para que su Happiness Manager pueda conversar antes de que la decisión esté tomada. (2) Desempeño o productividad sostenidamente por debajo de lo esperado —un nivel, no una tendencia de fuga— vía el canal `desarrollo`, como derivación a un plan de acompañamiento. Nunca se presenta como riesgo de fuga ni llega como alerta de bienestar: es soporte, no retención.

**Y qué no decide.** Una alerta es una invitación a conversar, no un juicio.
No entra a ningún proceso de desempeño, no cambia la evaluación de nadie y no
llega a quien decide sobre la carrera de la persona alertada.

Nunca recibe una alerta: **líder directo**, **cualquier sistema de evaluación de desempeño**.

## Universo

Se evalúa `employee_360` bajo la condición
`activo_en_el_mes AND antiguedad_meses >= 3`.

El corte no es estadístico, es contractual. En Buk todos entran con contrato a plazo fijo y a los 3 meses rinden una evaluación formal de desempeño sobre tres ejes: si representaron los valores, si demostraron ser competentes y si alcanzaron las métricas del cargo definidas en el plan de onboarding. Esa evaluación es el PRIMER dato estructurado que existe sobre la persona. El sistema empieza a mirar exactamente el día que hay algo que mirar; antes no hay una decisión que tomar con menos evidencia, hay ausencia de evidencia. Consecuencia que hay que decir en voz alta: durante los meses siguientes esa persona tiene un nivel de desempeño pero todavía no tiene un DELTA —hace falta una segunda evaluación—, y sus ventanas móviles operativas recién se completan. Es decir, el sistema la ve, pero la ve a medias. Ver `limitaciones` y la auditoría por tramo de antigüedad.


## Garantías verificadas en código

Estas no son promesas del documento: son seis validaciones que corren antes de
compilar el SQL. Si alguna falla, `motor.py` levanta `CatalogoInvalido` y no se
emite ninguna alerta. Un catálogo inválido no produce alertas malas — no
produce ninguna.

| # | Garantía | Por qué |
|---|---|---|
| 1 | Ninguna expresión menciona un atributo prohibido | La prohibición se verifica, no se confía |
| 2 | Toda señal referida por una regla existe en el catálogo | Una regla que apunta al vacío no falla: no dispara nunca, en silencio |
| 3 | **Toda rama de toda regla cruza ≥ 2 dimensiones** | Una sola dimensión es una métrica, no una lectura de una persona |
| 4 | Toda rama contiene ≥ 1 señal de tipo `riesgo` | Impide una alerta armada solo con contexto |
| 5 | Todo canal usado por una regla tiene capacidad declarada | Una alerta sin destinatario ni cupo es una alerta que nadie atiende |
| 6 | Las prioridades son únicas | La cola tiene que ser determinista para poder auditarse |

### Atributos prohibidos

`genero`, `nacionalidad`, `edad`, `tramo_edad`, `cargo`, `nombre`, `fecha_salida`, `tipo_salida`, `salida_lamentada`, `sale_en_3_meses`

No pueden aparecer en ninguna expresión de señal ni condición de regla. Sí se
miden en la auditoría de impacto dispar: la prohibición se paga con la
obligación de vigilar.

### Lista blanca de lectura

El SQL proyecta **26 columnas**, derivadas de las expresiones de las
señales más el contexto que la alerta necesita para explicarse. No es una lista
mantenida aparte: se calcula desde el catálogo. Lo que ninguna señal menciona,
no se selecciona — y por eso las etiquetas de salida (`fecha_salida`,
`sale_en_3_meses`) no pueden filtrarse aunque alguien las escriba por error.


## Dimensiones

| Dimensión | Qué observa |
|---|---|
| `compensacion` | Posición del sueldo dentro de la banda de su cargo |
| `desempeno` | Evaluación formal en la escala 1-4 de Buk |
| `operativa` | Productividad y CSAT del proceso, en ventanas móviles |
| `desgaste` | Señales de agotamiento y desconexión del ritmo de sus pares |

## Señales vigentes

Una señal de tipo `contexto` no puede fundar una alerta por sí sola: sirve para completar la segunda dimensión de una regla. `desempeno_sobresaliente` es contexto — nunca alerta a nadie, pero cambia por completo la lectura de un sueldo bajo banda.

| Señal | Dimensión | Tipo | Condición | Lift |
|---|---|---|---|---|
| `compa_bajo` | compensacion | riesgo | `compa_ratio < 0.9` | 2.27 |
| `bajo_banda` | compensacion | riesgo | `bajo_banda` | 3.29 |
| `caida_desempeno` | desempeno | riesgo | `delta_desempeno <= -0.2` | 1.62 |
| `desempeno_cumple` | desempeno | contexto | `score_vigente >= 3.0` | — |
| `desempeno_sobresaliente` | desempeno | contexto | `score_vigente >= 3.5` | — |
| `caida_productividad` | operativa | riesgo | `prod_delta_3m <= -3.0 AND meses_con_prod_3m >= 2` | 2.05 |
| `caida_productividad_pronunciada` | operativa | riesgo | `prod_delta_3m <= -4.0 AND meses_con_prod_3m >= 2` | 2.65 |
| `caida_csat` | operativa | riesgo | `csat_delta_3m <= -0.2` | 2.36 |
| `desgaste_vacaciones` | desgaste | riesgo | `dias_sin_vacaciones > ROUND(0.7 * antiguedad_meses * 30, 6)` | 1.11 |
| `desempeno_bajo_sostenido` | desempeno | riesgo | `score_vigente < 2.8` | — |
| `productividad_baja_sostenida` | operativa | riesgo | `prod_prom_3m < 85.0 AND meses_con_prod_3m >= 2` | — |

### Por qué cada señal está aquí

**`compa_bajo` — Sueldo bajo la mediana de su banda**  
Equidad Interna es uno de los cuatro lineamientos de compensación de Buk. La política opera en ciclos anuales con presupuesto y calibración; entre ciclo y ciclo se abre una ventana en la que alguien puede quedar bajo su banda sin que nadie lo esté mirando. Esta señal caza esa ventana.

**`bajo_banda` — Sueldo bajo el piso de su banda**  
Más grave que un compa-ratio bajo: no es estar en la parte baja del rango, es estar fuera de él. Es un incumplimiento de la propia política de bandas y se corrige aunque la persona no esté pensando en irse.

**`caida_desempeno` — Bajó respecto de su evaluación anterior**  
La trayectoria, no el nivel. Un nivel bajo sostenido ya lo gestiona el líder con un plan de acción por su propio canal; duplicarlo aquí convertiría la alerta en munición. Una caída en alguien que venía bien es información nueva.

**`desempeno_cumple` — Cumple o supera lo esperado**  
Delimita el objetivo declarado: retener a quien queremos retener. No es una señal de riesgo y por sí sola nunca alerta a nadie.

**`desempeno_sobresaliente` — Sobresaliente**  
Ser sobresaliente no es un problema: es lo que hace que su salida duela y que el mercado la busque. Entra como contexto que sube la prioridad de una señal de riesgo, nunca como motivo de alerta.

**`caida_productividad` — Productividad en descenso**  
Tendencia contra sí mismo, no contra un ranking: compara a la persona con su propio trimestre anterior. El requisito de 2 meses observados evita que un mes suelto de planilla incompleta dispare una alerta.

**`caida_productividad_pronunciada` — Productividad en descenso pronunciado**  
Misma métrica que `caida_productividad` con el corte más exigente. Existe como señal aparte porque habilita reglas que no requieren contexto de desempeño, y para eso el umbral tiene que sostener la precisión solo.

**`caida_csat` — Satisfacción del cliente en descenso**  
Solo aplica a roles de cara al cliente (~47% de la dotación). En el resto es nulo por NO APLICAR, no por falta de dato, y una comparación contra nulo nunca dispara. La calidad percibida cae antes que el volumen.

**`desgaste_vacaciones` — No toma vacaciones hace más tiempo que sus pares**  
Buk tiene vacaciones flexibles: no tomarlas es una decisión, no una restricción, y quien está desganado tiende a tomar MENOS. El denominador es el tiempo que la persona lleva en Buk, no el promedio de su cohorte: la versión por cohorte medía antigüedad disfrazada de conducta y salía con lift 0,90 — ver `senales_descartadas`.

**`desempeno_bajo_sostenido` — Desempeño bajo lo esperado**  
Nivel, no trayectoria — a propósito el mismo umbral que `desempeno_bajo` en `senales_descartadas`, con un destino distinto. Esa señal se descartó del catálogo completo en v1.0.0 porque metida en el canal de retención construye un detector de bajo desempeño con etiqueta de bienestar. Aquí solo alimenta la regla R06, que enruta a `desarrollo`, nunca a `conversacion`: el dato es el mismo, el canal y la lectura no.

**`productividad_baja_sostenida` — Productividad sostenida bajo el proceso**  
Cierra el hueco que medía la tabla de techo de cobertura: `caida_productividad` exige una caída reciente y no ve a quien lleva tiempo sostenido bajo el proceso sin haber caído desde más arriba. Es la mitad "baja productividad" del mandato del caso, tratada como su propio problema — no como síntoma de una fuga probable.


## Señales descartadas

La sección más importante del catálogo. Documenta lo que se probó y se sacó, con
el número que lo justifica. Un catálogo que solo muestra lo que quedó no permite
distinguir un diseño de una colección de intuiciones que sobrevivieron.

La columna que decide es **lift sobre salida lamentada**. `lift ≈ 1` significa
indistinguible del azar; `lift < 1` significa que la señal predice lo contrario
de lo que buscamos.

| Señal | Condición | Lift lamentada | Lift cualquier salida |
|---|---|---|---|
| `desempeno_bajo` | `score_vigente < 2.8` | **0.48** | 2.51 |
| `riesgo_evaluacion_90d` | `score_90d < 3.0 AND antiguedad_meses <= 12` | **0.72** | — |
| `sueldo_sin_revisar` | `meses_desde_ultimo_ajuste >= 18` | **0.79** | — |
| `formacion_bajo_cohorte` | `ratio_formacion_cohorte < 0.5` | **1.04** | — |
| `desgaste_vacaciones_por_cohorte` | `ratio_vacaciones_cohorte > 1.5` | **0.9** | — |

**`desempeno_bajo`**  
LA decisión de diseño del bloque. Predice muy bien las salidas —y muy mal las que duelen: quien está bajo lo esperado y se va no es una pérdida que People Happiness deba prevenir por retención, y ya tiene un canal con su líder para el proceso de desempeño. Una regla escrita sobre esta señal DENTRO DEL CANAL DE RETENCIÓN habría producido un detector de bajo desempeño con etiqueta de bienestar, que es exactamente el sesgo punitivo que el diseño debe evitar. La estadística y la ética coinciden ahí. **Revisado en v1.1.0, no revertido.** El error de v1.0.0 no fue descartar esta señal del canal de retención —eso sigue siendo correcto— fue descartarla también del catálogo completo, dejando sin ningún canal la mitad "baja productividad" del mandato del caso (medido: 0.0% de cobertura sobre los perfiles de baja productividad sostenida). Vuelve al catálogo como `desempeno_bajo_sostenido`, enrutada exclusivamente a `desarrollo` (panel de soporte, nunca alerta de retención) vía R06. Nunca se combina para gatillar `conversacion`.

**`riesgo_evaluacion_90d`**  
Mismo problema que la anterior, en la puerta de entrada, y ahora sabemos exactamente por qué. La evaluación de los 3 meses es la que decide si el contrato a plazo fijo se renueva: quien puntúa bajo tiende a salir porque LA EMPRESA no lo renueva, no porque él se vaya. Esa salida no es lamentada por definición. El lift de 0,72 no es un accidente del dato sintético: es lo que la estructura contractual predice. El valor de esa evaluación para nosotros está en el otro extremo. Quien pasó los 3 meses con nota alta ES exactamente el perfil que no queremos perder, y su score alimenta `desempeno_cumple` y `desempeno_sobresaliente` —las dos señales de contexto que completan las reglas de compensación— desde el primer mes en que el sistema lo puede mirar. La evaluación de 90 días entra al catálogo, pero como contexto positivo, nunca como riesgo.

**`sueldo_sin_revisar`**  
Argumento intuitivo impecable —"gana poco y nadie lo ha mirado"— y dato que apunta al revés. Está confundido con antigüedad: quien lleva menos tiempo tuvo su ajuste hace menos meses y es quien más se va. Estratificado por tramo de antigüedad sigue bajo 1 en tres de los cuatro tramos.

**`formacion_bajo_cohorte`**  
Indistinguible del azar. Dispara en el 32% de las personas-mes: como condición habría inflado el volumen sin aportar información.

**`desgaste_vacaciones_por_cohorte`**  
La normalización por cohorte de antigüedad no alcanzó: el tramo 0-11 meses es demasiado ancho y dentro de él el ratio sigue midiendo cuántos meses lleva la persona. Reemplazada por `desgaste_vacaciones`, que divide por el tiempo efectivamente disponible para tomarlas y sube de 0,90 a 1,11.


## Reglas vigentes

El orden de prioridad no es una opinión sobre qué duele más: es el ranking de
precisión medida en el backtest. Se recalcula en cada revisión trimestral, y una
regla puede bajar de puesto sin que nadie la haya cambiado.

| # | Regla | Canal | Nivel | Condición |
|---|---|---|---|---|
| 1 | **R01** Deterioro en dos frentes | conversacion | alto | `s_caida_desempeno AND (s_caida_productividad OR s_caida_csat)` |
| 2 | **R02** Fuera de banda cumpliendo | compensaciones | alto | `s_bajo_banda AND s_desempeno_cumple` |
| 3 | **R03** Desenganche operativo | conversacion | alto | `s_caida_productividad_pronunciada AND (s_compa_bajo OR s_desgaste_vacaciones OR s_caida_desempeno)` |
| 4 | **R05** Talento sobresaliente bajo banda | compensaciones | medio | `s_compa_bajo AND s_desempeno_sobresaliente` |
| 5 | **R04** Servicio y desgaste | desarrollo | medio | `s_caida_csat AND (s_compa_bajo OR s_desgaste_vacaciones)` |
| 6 | **R06** Desempeño y productividad sostenidamente bajos | desarrollo | medio | `s_desempeno_bajo_sostenido AND (s_productividad_baja_sostenida)` |

### Qué dice cada regla y qué se hace con ella

**R01 · Deterioro en dos frentes**  
*Lectura:* Bajó en su evaluación formal y además su operación se está deteriorando. Dos sistemas de medición independientes dicen lo mismo.  
*Acción sugerida:* Conversación de escucha en los próximos 10 días hábiles. Explorar carga, claridad de expectativas y contexto personal antes de cualquier hipótesis de desempeño.

**R02 · Fuera de banda cumpliendo**  
*Lectura:* Cumple o supera lo esperado y su sueldo está bajo el piso de su propia banda. Es un incumplimiento de la política de compensación, no una hipótesis sobre la persona.  
*Acción sugerida:* Derivar a Compensaciones para revisión de banda en el ciclo vigente. La conversación con la persona solo después de tener una respuesta.

**R03 · Desenganche operativo**  
*Lectura:* Caída sostenida de productividad acompañada de una segunda señal de otra dimensión. La caída sola no alerta: podría ser estacionalidad del proceso.  
*Acción sugerida:* Revisar con el líder si hubo cambio de alcance, equipo o cliente en el trimestre antes de agendar la conversación.

**R05 · Talento sobresaliente bajo banda**  
*Lectura:* Sobresaliente y pagado bajo la mediana de su banda. Hoy no muestra deterioro: es exactamente por eso que una regla de desempeño nunca lo vería.  
*Acción sugerida:* Revisar posición en banda en la próxima calibración de mérito. Sin conversación de riesgo: no hay evidencia de que quiera irse.

**R04 · Servicio y desgaste**  
*Lectura:* La calidad percibida por sus clientes está bajando y hay una segunda señal de contexto. En roles de cara al cliente el CSAT suele moverse antes que cualquier métrica de volumen.  
*Acción sugerida:* Incluir en la agenda del próximo 1:1 del HM. No requiere gestión inmediata.

**R06 · Desempeño y productividad sostenidamente bajos**  
*Lectura:* Su desempeño y su productividad llevan tiempo sostenidos por debajo de lo esperado, sin una caída reciente que lo explique: es un nivel, no una tendencia de fuga. No implica que la persona quiera irse.  
*Acción sugerida:* Derivar a Aprendizaje y Desarrollo para definir un plan de acompañamiento junto al líder. No es una conversación de riesgo de fuga: es soporte para cerrar la brecha.


## Operación

La distinción que ordena todo el bloque es **evento vs estado**.

Un evento —la productividad cayó, la evaluación bajó— pasó una vez y hay una
ventana para reaccionar. Repetirlo cada mes no agrega información y quema la
atención de quien lo recibe: por eso lleva enfriamiento y tope de capacidad.

Un estado —está pagado bajo el piso de su banda— es cierto hoy y lo seguirá
siendo mañana hasta que alguien lo arregle. Ponerle enfriamiento sería dejar de
mirar un problema que no se movió. Va a un panel que se lee entero, sin tope:
un panel no consume atención por caso.

| Canal | Modo | Cupo mensual | Enfriamiento | Destinatario |
|---|---|---|---|---|
| `conversacion` | alerta | 35 | 3 meses | Happiness Manager del área |
| `compensaciones` | panel | sin tope | sin enfriamiento | Compensaciones, con copia al Happiness Manager |
| `desarrollo` | panel | sin tope | sin enfriamiento | Aprendizaje y Desarrollo, con copia al Happiness Manager |

**Desempate de la cola:** `prioridad`, `compa_ratio`, `employee_id`.

El enfriamiento tiene una excepción: si la persona reaparece por una regla de
**mayor** prioridad, la alerta pasa igual. Silenciar una escalada sería el peor
efecto posible de un mecanismo pensado para reducir ruido.


## Qué produce este catálogo

> **Advertencia que va antes de los números.** Estos resultados vienen de datos
> sintéticos con estructura causal conocida: el generador puso ahí las
> relaciones que el backtest encuentra. Esto valida el *método* —que la tubería
> corre, que las métricas se calculan sobre la población correcta, que la
> censura está bien tratada—. No es evidencia de que el sistema funcione en
> Buk. Eso solo lo dice una corrida sobre datos reales.

Ventana de acierto: **6 meses**. Se evalúa hasta **2026-02** aunque el
dato llegue a **2026-08**: nadie puede salir en 6 meses si solo quedan
6 meses de historia (censura a la derecha).

| Métrica | Valor | Lectura |
|---|---|---|
| Carga | **28.7 alertas/mes** | contra un cupo de 35 |
| Precisión (salida lamentada) | **14.1%** | base 4.5% · **lift 3.10x** |
| Precisión (cualquier salida) | 18.6% | base 7.8% · lift 2.38x |
| Cobertura | **47 de 341 = 13.8%** | salidas lamentadas alcanzadas antes |
| Costo sobre quien se queda | 314 de 2,000 = **15.7%** | apareció en una alerta y sigue en Buk |

La última fila es la que casi nunca se muestra y la que más importa: cada
persona ahí es alguien que no se iba y aun así llegó a una lista. Es el precio
del sistema, y se publica junto al beneficio.

### Techo de cobertura

| perfil | salidas_lamentadas | cubiertas | cobertura_pct |
|---|---|---|---|
| estable | 141 | 7 | 5.0 |
| deterioro | 108 | 15 | 13.9 |
| estrella_subpagada | 88 | 25 | 28.4 |
| bajo_desempeno | 2 | 0 | 0.0 |
| nuevo_dificil | 2 | 0 | 0.0 |

El **41%** de las salidas lamentadas viene del perfil `estable`: gente sin
deterioro previo por construcción —una oferta inesperada, una mudanza, un cambio
de vida—. Ninguna regla, y ningún modelo, la ve venir. **La cobertura máxima
alcanzable es ~59%**, y decirlo por adelantado es parte del diseño: un
sistema que prometiera detectar el 100% describiría un mundo donde las personas
son predecibles.

### Alcance del panel `desarrollo`

La mitad "baja productividad" del mandato del caso, cerrada en v1.1.0. No es
una métrica de predicción de salida —este canal no existe para eso—: mide, de
cada perfil latente, qué fracción de TODA su población (no solo quien salió)
aparece alguna vez en el panel mientras sigue en Buk.

| perfil | total_personas | en_panel_desarrollo | cobertura_pct |
|---|---|---|---|
| estable | 1896 | 144 | 7.6 |
| bajo_desempeno | 138 | 49 | 35.5 |
| estrella_subpagada | 225 | 34 | 15.1 |
| deterioro | 320 | 24 | 7.5 |
| nuevo_dificil | 71 | 11 | 15.5 |

En v1.0.0 `bajo_desempeno` y `nuevo_dificil` estaban en **0.0%** de cobertura
en todo canal — la señal que los alcanzaba (`desempeno_bajo`) había sido
descartada del catálogo completo, no solo del canal de retención. R06 los
alcanza en **35.5%** y
**15.5%** respectivamente,
con baja fuga hacia perfiles que no debería tocar (`estable` en
7.6%).


## Curva de calibración

La respuesta honesta a *"¿por qué 35 y no 100?"*. No es que 35 maximice algo:
es lo que People Happiness puede atender de verdad. La tabla muestra exactamente
cuánta cobertura cuesta esa restricción, con enfriamiento de 3 meses.

| Cupo | Alertas/mes | Precisión % | Lift | Cobertura % | Carga falsa % |
|---|---|---|---|---|---|
| 15 | 14.67 | 15.38 | 3.38 | 6.45 | 8.30 |
| 25 | 22.53 | 14.89 | 3.27 | 11.44 | 12.40 |
| 35 | 28.67 | 14.09 | 3.10 | 13.78 | 15.70 |
| 50 | 33.93 | 13.25 | 2.91 | 14.66 | 18.90 |
| 75 | 35.73 | 13.25 | 2.91 | 14.66 | 20.00 |
| 100 | 35.93 | 13.25 | 2.91 | 14.66 | 20.15 |
| 150 | 35.93 | 13.25 | 2.91 | 14.66 | 20.15 |
| 9999 | 35.93 | 13.25 | 2.91 | 14.66 | 20.15 |

Lo que dice la curva: la cobertura **satura**. Multiplicar el cupo por cuatro no
multiplica la cobertura — agrega alertas cada vez peores sobre gente que se
queda. El cupo no es el cuello de botella; el poder de las señales sí.

### El enfriamiento es la palanca, no el cupo

El efecto del enfriamiento hay que medirlo **sin tope**, porque con tope el cupo
lo esconde: al recortar repeticiones, el enfriamiento simplemente deja entrar a
otra persona y el volumen no se mueve.

| Enfriamiento (meses) | Alertas/mes | Precisión % | Cobertura % | Carga falsa % |
|---|---|---|---|---|
| 0 | 58.13 | 16.57 | 14.96 | 20.15 |
| 3 | 35.93 | 13.25 | 14.66 | 20.15 |
| 6 | 34.27 | 13.48 | 14.37 | 20.15 |

Ahí se ve el argumento entero del bloque: pasar de 0 a 3 meses de enfriamiento
elimina el **38% del volumen** y cuesta **0,3 puntos de
cobertura**. La fracción de gente que se queda y aparece alertada no cambia en absoluto (20,15% en los tres casos):
son exactamente las mismas personas, avisadas menos veces.

Ese es el hallazgo que ordenó la calibración. El problema nunca fue que los
umbrales estuvieran bajos —subirlos habría costado cobertura real—: era que el
sistema le repetía a la misma persona la misma alerta todos los meses. Se
arregló dejando de repetir, no dejando de mirar.


## Auditoría de impacto dispar

Se prohíbe usar un atributo protegido como condición **y** se obliga a medir
sobre quién cae el sistema. Lo primero sin lo segundo es una garantía de papel:
un modelo puede discriminar sin nombrar nunca al grupo que discrimina, porque
las variables que sí usa están correlacionadas con él.

Se miden tres cosas, y la distinción importa más que los números:

- **Paridad demográfica** — ¿alertamos parejo? Es la métrica intuitiva y es
  insuficiente sola: si un grupo tiene más riesgo real, alertarlo más es hacer
  el trabajo.
- **Igualdad de oportunidad** — de quienes salieron doliendo, ¿a qué fracción
  llegamos en cada grupo? Esta es la métrica ética: mide el reparto del
  beneficio, no el del castigo.
- **Exposición** — nadie puede ser alertado un mes en que no era elegible. La
  tasa se calcula por mes-persona expuesto; medirla por cabeza compara gente que
  corrió distancias distintas.

Se marca un grupo cuando el índice sale de [0.80, 1.25]
(regla del 80%, EEOC) **y además** la diferencia supera lo que el azar binomial
explica (dos proporciones, |z| > 2). Las dos condiciones
juntas, no una: marcar de más entrena al comité a ignorar la lista. Grupos bajo
40 personas se agregan; el índice de cobertura solo se publica con
al menos 25 salidas lamentadas.


### Atributos protegidos

**`genero`**

| Grupo | Personas | Meses expuesto | Alertas/1.000 meses | Tasa salida lam. | Salidas lam. | Cobertura | Índice alerta | Índice cobertura | Estado |
|---|---|---|---|---|---|---|---|---|---|
| F | 1391 | 10.606 | 15.048 | 0.129 | 180 | 0.122 | 1.000 | 1.000 | referencia |
| M | 1142 | 10.443 | 16.435 | 0.137 | 157 | 0.159 | 1.092 | 1.303 | ok |
| No binario / No informa | 48 | 10.167 | 24.590 | 0.083 | 4 | n/d | 1.634 | n/d | ok |

**`tramo_edad`**

| Grupo | Personas | Meses expuesto | Alertas/1.000 meses | Tasa salida lam. | Salidas lam. | Cobertura | Índice alerta | Índice cobertura | Estado |
|---|---|---|---|---|---|---|---|---|---|
| 26-35 | 1401 | 10.231 | 15.489 | 0.130 | 182 | 0.115 | 1.000 | 1.000 | referencia |
| <26 | 603 | 11.312 | 16.566 | 0.133 | 80 | 0.175 | 1.070 | 1.517 | ok |
| 36-45 | 554 | 10.462 | 16.218 | 0.141 | 78 | 0.154 | 1.047 | 1.333 | ok |
| otros (n < 40) | 23 | 9.435 | 4.608 | 0.043 | 1 | n/d | 0.298 | n/d | ok |

**`nacionalidad`**

| Grupo | Personas | Meses expuesto | Alertas/1.000 meses | Tasa salida lam. | Salidas lam. | Cobertura | Índice alerta | Índice cobertura | Estado |
|---|---|---|---|---|---|---|---|---|---|
| Chilena | 824 | 10.964 | 13.726 | 0.121 | 100 | 0.100 | 1.000 | 1.000 | referencia |
| Colombiana | 321 | 10.452 | 16.095 | 0.165 | 53 | 0.132 | 1.173 | 1.321 | ok |
| otros (n < 40) | 316 | 10.082 | 16.008 | 0.142 | 45 | 0.156 | 1.166 | 1.556 | ok |
| Mexicana | 315 | 10.860 | 19.293 | 0.117 | 37 | 0.297 | 1.406 | 2.973 | REVISAR: alerta, cobertura |
| Peruana | 247 | 10.166 | 19.912 | 0.105 | 26 | 0.077 | 1.451 | 0.769 | REVISAR: alerta |
| Argentina | 166 | 9.831 | 17.157 | 0.139 | 23 | n/d | 1.250 | n/d | ok |
| Venezolana | 147 | 9.789 | 12.509 | 0.116 | 17 | n/d | 0.911 | n/d | ok |
| Brasileña | 143 | 11.462 | 15.253 | 0.147 | 21 | n/d | 1.111 | n/d | ok |
| Ecuatoriana | 53 | 9.547 | 11.858 | 0.113 | 6 | n/d | 0.864 | n/d | ok |
| Española | 49 | 9.061 | 18.018 | 0.265 | 13 | n/d | 1.313 | n/d | ok |


### Ejes de gobernanza (no protegidos)

**`job_family`**

| Grupo | Personas | Meses expuesto | Alertas/1.000 meses | Tasa salida lam. | Salidas lam. | Cobertura | Índice alerta | Índice cobertura | Estado |
|---|---|---|---|---|---|---|---|---|---|
| Ingeniería | 504 | 10.581 | 16.314 | 0.141 | 71 | 0.113 | 1.000 | 1.000 | referencia |
| Ventas | 363 | 9.975 | 15.742 | 0.171 | 62 | 0.129 | 0.965 | 1.145 | ok |
| Customer Success | 337 | 10.439 | 17.908 | 0.098 | 33 | 0.091 | 1.098 | 0.807 | ok |
| Soporte | 295 | 10.420 | 13.663 | 0.108 | 32 | 0.094 | 0.838 | 0.832 | ok |
| Implementación | 266 | 10.778 | 16.393 | 0.120 | 32 | 0.219 | 1.005 | 1.941 | ok |
| Operaciones | 171 | 11.251 | 15.593 | 0.140 | 24 | n/d | 0.956 | n/d | ok |
| Personas | 137 | 10.409 | 21.739 | 0.139 | 19 | n/d | 1.333 | n/d | ok |
| Finanzas | 130 | 10.177 | 12.850 | 0.138 | 18 | n/d | 0.788 | n/d | ok |
| Producto | 127 | 10.811 | 17.480 | 0.126 | 16 | n/d | 1.072 | n/d | ok |
| Marketing | 115 | 11.000 | 6.324 | 0.148 | 17 | n/d | 0.388 | n/d | REVISAR: alerta |
| Datos | 96 | 11.219 | 15.785 | 0.135 | 13 | n/d | 0.968 | n/d | ok |
| Legal | 40 | 9.150 | 19.126 | 0.100 | 4 | n/d | 1.172 | n/d | ok |

**`pais_contrato`**

| Grupo | Personas | Meses expuesto | Alertas/1.000 meses | Tasa salida lam. | Salidas lam. | Cobertura | Índice alerta | Índice cobertura | Estado |
|---|---|---|---|---|---|---|---|---|---|
| CL | 1425 | 10.413 | 15.164 | 0.121 | 173 | 0.116 | 1.000 | 1.000 | referencia |
| MX | 405 | 10.728 | 16.801 | 0.160 | 65 | 0.185 | 1.108 | 1.597 | ok |
| CO | 326 | 10.877 | 12.972 | 0.123 | 40 | 0.125 | 0.855 | 1.081 | ok |
| PE | 244 | 10.496 | 15.228 | 0.135 | 33 | 0.121 | 1.004 | 1.048 | ok |
| BR | 181 | 10.370 | 25.040 | 0.166 | 30 | 0.200 | 1.651 | 1.730 | REVISAR: alerta |

**`tramo_antiguedad`**

| Grupo | Personas | Meses expuesto | Alertas/1.000 meses | Tasa salida lam. | Salidas lam. | Cobertura | Índice alerta | Índice cobertura | Estado |
|---|---|---|---|---|---|---|---|---|---|
| 0-11 | 1079 | 3.565 | 16.636 | 0.194 | 209 | 0.081 | 1.000 | 1.000 | referencia |
| 12-23 | 672 | 13.853 | 19.658 | 0.092 | 62 | 0.290 | 1.182 | 3.569 | REVISAR: cobertura |
| 24-47 | 533 | 16.769 | 14.657 | 0.096 | 51 | 0.216 | 0.881 | 2.652 | REVISAR: cobertura |
| 48+ | 297 | 17.081 | 10.250 | 0.064 | 19 | n/d | 0.616 | n/d | REVISAR: alerta |


### Hallazgos de esta corrida

7 grupo(s) fuera de banda. No es un veredicto: es la lista de lo que
hay que mirar antes de publicar esta versión.

- `nacionalidad` = **Mexicana** — REVISAR: alerta, cobertura
- `nacionalidad` = **Peruana** — REVISAR: alerta
- `job_family` = **Marketing** — REVISAR: alerta
- `pais_contrato` = **BR** — REVISAR: alerta
- `tramo_antiguedad` = **12-23** — REVISAR: cobertura
- `tramo_antiguedad` = **24-47** — REVISAR: cobertura
- `tramo_antiguedad` = **48+** — REVISAR: alerta

**Cómo se lee una desviación, en orden.** El protocolo importa más que
cualquier hallazgo puntual, porque es lo que impide dos errores opuestos:
corregir un sesgo que no existe, y tapar uno que sí.

1. **¿La tasa de salida real del grupo también es distinta?** Entonces el
   sistema está siguiendo el riesgo, no creándolo.
2. **¿Hay una señal cuya métrica de origen se comporta distinto en ese grupo?**
   El problema está en la métrica, no en la gente.
3. **Recién entonces: revisar umbrales.** Nunca añadir el atributo como
   condición.

Aplicado a lo marcado arriba:

- **`nacionalidad` = Mexicana** (índice de alerta 1,41, índice de cobertura
  2,97). Atributo protegido, así que el estándar de prueba es más alto. El
  desvío de cobertura es a favor y es grande: de quienes salieron doliendo se
  alcanza a casi tres veces la fracción del grupo de referencia. El de alerta
  queda abierto: con tasa de salida 0,117 —por debajo de la referencia (0,121)—
  el paso 1 no lo explica. Se registra, se revisa el próximo trimestre y con
  37 salidas lamentadas todavía puede ser ruido que el test no descarta.
- **`nacionalidad` = Peruana** (índice de alerta 1,45, índice de cobertura
  0,77). **Este es el hallazgo abierto de la corrida y el que impide publicar
  esta versión sin revisión.** Ninguno de los tres pasos lo cierra. El paso 1 lo
  contradice: la tasa de salida lamentada del grupo es 0,105, la más baja entre
  los grupos grandes y por debajo de la referencia chilena (0,121) — se alerta
  45% más a un grupo que se va menos. El paso 2 explica de dónde salen las
  alertas pero no las justifica: las métricas de origen sí se deterioran más
  (caída de productividad a 3 meses −0,394 contra −0,276 en el grupo de
  referencia, caída de CSAT −0,020 contra −0,010), y la mezcla de familias de
  cargo no lo produce —Perú pesa más en Soporte, que es la familia con **menos**
  alertas por exposición—. Queda una señal que se mueve sin que el resultado la
  siga. Hasta entenderlo, la versión no se despliega sola: es exactamente el
  caso que el veto de auditoría existe para detener.
- **`job_family` = Marketing** (índice de alerta 0,39). Paso 2. Marketing no
  tiene CSAT —no es cara al cliente— y su métrica de productividad es la menos
  dispersa de la compañía (sd 2,41 contra 2,7 típico) y la que menos deriva a la
  baja (−0,10 contra −0,37). Tres de las cinco reglas le son inalcanzables en la
  práctica, y el umbral absoluto de caída (−3,0 puntos) casi no se activa en una
  métrica que no se mueve. **Está sub-detectada por instrumentación, no por
  sesgo.** Corregirlo pide normalizar la caída de productividad dentro de la
  familia, y eso es un cambio de catálogo con backtest propio, no un parche.
- **`pais_contrato` = BR** (índice de alerta 1,65). Paso 1 lo resuelve: Brasil
  tiene la mayor tasa de salida lamentada (0,166) y el `compa_ratio` medio más
  bajo (0,965), con 3,7% de dotación bajo banda contra 1,2% en Chile. El sistema
  no está sesgado contra Brasil: está encontrando un problema de estructura
  salarial en Brasil. El hallazgo es para Compensaciones, no para el catálogo.
- **`tramo_antiguedad`** (cobertura de 12-23 y 24-47 sobre 0-11, índices 3,57 y
  2,65). Ver la limitación declarada más abajo: es exposición, y es el hallazgo
  más importante de esta corrida.
- **`tramo_antiguedad` = 48+** (índice de alerta 0,62). Paso 1 lo resuelve en el
  sentido contrario al de Brasil: quienes llevan cuatro años o más tienen la
  **menor** tasa de salida lamentada de la compañía (0,064 contra 0,194 del tramo
  0-11). Se les alerta menos porque se van menos.

**2 grupo(s) de atributo protegido quedaron marcados por índice de alerta** (`nacionalidad` = Mexicana, `nacionalidad` = Peruana). No es prueba de que el sistema discrimine —el índice mide alertas, no daño— pero sí es la condición que obliga a revisar antes de publicar, y no se levanta sola.


## Limitaciones declaradas

Se declaran acá para que se discutan, no para que se descubran.

### 1. El sistema casi no ve a quien recién llegó — y es quien más se va

El hallazgo más incómodo de la auditoría. La cohorte de 0-11 meses tiene la
**mayor** tasa de salida lamentada (0,194 contra
0,092 del siguiente tramo) y concentra el **61% de todas
las salidas lamentadas**. Su cobertura es 8,1%.

Medido por cabeza parecía un sesgo brutal: 4,6x menos alertas que el
tramo siguiente. Medido por mes-persona expuesto se da vuelta: 16,6 alertas
por cada mil meses contra 19,7 del tramo 12-23 — a quien está en el
universo se le alerta prácticamente al mismo ritmo que a todos. La diferencia
entera es tiempo: un recién llegado está en el universo **3,6 meses** en
promedio, contra **13,9** del tramo siguiente.

No es un defecto de las reglas: es que las reglas necesitan historia. Las
ventanas móviles piden 3 meses, la caída de evaluación pide dos evaluaciones, y
el universo empieza a los 3 meses de antigüedad. Cuando el sistema puede
observar a alguien, esa persona ya se fue.

**Por qué no se arregla con el panel de compensaciones.** Las reglas de
compensación sí alcanzan a un recién llegado: `compa_ratio` existe desde el día
uno y la evaluación de los 3 meses le da un nivel de desempeño. Se midió: sumar
el panel recupera **3 de las 210 salidas lamentadas** de la
cohorte —**1,4 puntos de cobertura**—. Ayuda, no resuelve.

**Qué le falta exactamente.** No le falta *una* señal: le falta la *segunda*
evaluación. Con contrato a plazo fijo y evaluación formal a los 3 meses, un
recién llegado tiene nivel de desempeño pero no tiene delta, y las tres reglas
del canal de conversación se apoyan en deltas. El sistema lo ve quieto y no lo
ve moverse.

**Consecuencia:** este catálogo no es un instrumento de onboarding y no debe
venderse como tal. El riesgo temprano necesita un instrumento propio que no
dependa de comparar contra el pasado. El más barato está a la mano: la
evaluación de 3 meses ya mide **tres ejes separados** —valores, competencias y
métricas del cargo—. Si se leen por separado en vez de agregados en un score,
son tres dimensiones de evidencia disponibles en el mes 3, suficientes para
fundar una regla de onboarding sin ninguna serie de tiempo. Es la primera línea
del roadmap, y es una línea concreta.

### 2. Los datos son sintéticos

El generador puso las relaciones causales que el backtest encuentra. Lo validado
es el método, no el resultado. Los umbrales de este catálogo son puntos de
partida razonados, no valores calibrados sobre Buk.

### 3. La cobertura tiene techo y no es alto

Cerca del 41% de las salidas lamentadas no tiene ninguna señal previa por
construcción. Con datos reales el techo será otro, pero existirá igual.

### 4. Una alerta correcta no es una retención

Todo lo que este documento mide termina en "se abrió una conversación a tiempo".
Si esa conversación sirve depende de qué pase en ella, y eso no lo mide ninguna
tabla de este documento.

### 5. El panel `desarrollo` (v1.1.0) todavía no pasó por la auditoría de equidad

`equidad.py` audita hoy el canal `conversacion` porque ahí nació el catálogo.
El panel `desarrollo`, agregado en v1.1.0 para cerrar la mitad "baja
productividad" del mandato, usa dos señales de NIVEL (no de tendencia) —
`score_vigente` y `prod_prom_3m` absolutos— que son precisamente el tipo de
métrica más expuesta a diferencias de instrumentación entre `job_family` (ver
el hallazgo de Marketing en la sección anterior, sobre una señal de tendencia).
No auditar esto antes de publicar sería repetir, en el canal nuevo, el mismo
error que esta versión corrigió en el canal viejo: declarar una garantía sin
medirla. Queda como el primer punto del roadmap, no como un supuesto.


## Bitácora de versiones

Buk registró 325 cambios internos en un año y los deja escritos. Un catálogo que
decide sobre personas se sostiene con la misma disciplina: cada cambio de umbral
queda con fecha, autor y motivo, y el backtest y la auditoría se archivan con la
versión. Sin esto, "revisamos trimestralmente" es una intención.

**v1.0.0 · 2026-08-31 · People Analytics**  
Catálogo inicial. Objetivo fijado en salida lamentada (no en salida a secas) tras medir que las señales de bajo desempeño predicen salidas NO lamentadas: optimizar contra "salida" habría construido un detector de bajo desempeño. Ver `senales_descartadas`.

**v1.1.0 · 2026-08-31 · People Analytics**  
El objetivo v1.0.0 cubría solo la mitad del mandato del caso ("riesgo de desvinculación") y dejaba la otra mitad ("baja productividad") sin ningún canal: la tabla de techo de cobertura medía 0.0% para los perfiles de baja productividad sostenida, porque `desempeno_bajo` había sido descartado del catálogo completo, no solo del canal de retención. Se agregan `desempeno_bajo_sostenido` y `productividad_baja_sostenida` (señales de NIVEL, no de tendencia) y la regla R06, enrutadas a un canal nuevo (`desarrollo`, modo panel) que nunca se presenta como riesgo de fuga. El razonamiento de v1.0.0 sobre no convertir bajo desempeño en una alerta de bienestar sigue vigente: lo que cambia es que ahora existe un canal de soporte que no es una alerta de bienestar ni de retención.

**v1.1.1 · 2026-09-01 · People Analytics**  
No es una recalibración: ningún umbral ni regla cambia de sentido. Al verificar el motor corriendo contra BigQuery (migración a la nube, F3) se encontraron dos comparaciones sensibles a no-determinismo de punto flotante entre motores — `desgaste_vacaciones` comparaba contra `0.7 * antiguedad_meses * 30` sin redondear, y una persona/mes cruzaba el umbral en un motor y no en el otro por una diferencia de ~1e-14 — y un desempate (`operacion.desempate`) que no formaba un orden total: `[prioridad, compa_ratio]` deja indefinido el orden entre dos personas empatadas en ambos, y cada motor lo resolvía distinto. Se agregó `ROUND(..., 6)` al lado derecho de la comparación en `desgaste_vacaciones` y `employee_id` como tercer nivel de `desempate`. Verificado con `cloud/verificar.py`: 0 celdas distintas entre DuckDB y BigQuery en `employee_360` y en `alertas` tras el cambio. No se corrieron `backtest.py`/`equidad.py`: el efecto medido en local fue candidatas 2.062 → 2.067 sobre 31.954 filas de `employee_360` (0,24%), y ningún umbral de negocio se tocó — se juzgó desproporcionado frente al costo de un backtest completo por un fix de estabilidad numérica. Detalle completo en `cloud/README.md`, sección F3.

**v1.1.2 · 2026-09-01 · People Analytics**  
R04 se mueve del canal `conversacion` (alerta) al canal `desarrollo` (panel de soporte). No es una recalibración: es una corrección de diseño. Contexto: la capacidad mensual de `conversacion` es 35 (equipo de una decena de personas). En agosto 2026 se registraron 65 candidatas totales, distribuidas como R01 22/22 (100%), R03 13/31 (42%), R04 0/12 (0%). R04 no gana un cupo desde febrero — 7 meses en `lista_seguimiento` pese a generar candidatas cada mes. Causa: motor ordena estrictamente por prioridad (R01 prioridad 1, R03 prioridad 3, R04 prioridad 5) sin mecanismo de envejecimiento — si R01+R03 agotan el cupo, R04 pierde determinísticamente. Decisión: R04 viola el contrato de su propio canal. Su `accion_sugerida` dice "No requiere gestión inmediata" — un texto de panel, no de alerta urgente de conversación. Su lectura describe un contexto (CSAT bajando en roles de cara al cliente) sin recomendación de retención. Lo honesto es moverla al canal `desarrollo`, donde su evidencia de CSAT+desgaste se atiende como soporte en el ciclo de Aprendizaje y Desarrollo, no como competencia contra reglas de salida lamentada. Verificación: la métrica "qué % de candidatas se sirven por regla" mejora automáticamente (R04 deja de competir por un cupo que no puede ganar). La probabilidad de que una persona caiga en `lista_seguimiento_sin_notificar` por R04 va de ~100% a 0%. Backtest.py y equidad.py rerun obligatorio por gobernanza (reglas.yaml:12).
