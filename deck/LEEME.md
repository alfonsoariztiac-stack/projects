# Deck del caso práctico · Buk

## Qué se presenta

`presentacion.html` — **un solo archivo, se abre con doble clic**. Sin CDN, sin fuentes
remotas, sin backend, sin red. Verificado con Playwright: cero peticiones externas.

## Controles

| Tecla | Qué hace |
|---|---|
| `→` `espacio` | Avanza un beat, y cambia de slide cuando se acaban |
| `←` | Retrocede |
| `↓` `↑` | Salta de slide sin pasar por los beats |
| `1`–`5` | Va directo a una slide, con todos sus beats abiertos |
| `N` | Notas del orador (guion + minutos + preguntas difíciles con su respuesta) |
| `C` | Guion de la salida a la nube, entre la slide 3 y la 4 |
| `T` | Reinicia el cronómetro |
| `?` | Ayuda |

El cronómetro parte con la primera tecla y muestra `transcurrido ▸ objetivo de la slide`.
Se pone ámbar si vas atrasado respecto de la slide siguiente.

La salida a la nube (`C`, entre la 3 y la 4) no tiene slide propia, así que el reloj no la mide.
Al cerrar el overlay, presiona `T` para reiniciar el cronómetro antes de seguir a la S4.

**Si la presentación es online:** las notas (`N`) y el guion de la nube (`C`) se muestran dentro
de esta misma ventana. No las abras si estás compartiendo esta pestaña.

## Recorrido

31 pasos en total: **4 · 3 · 7 · 3 · 14**. La salida a la nube va entre la 3 y la 4.

1. El problema y la tesis
2. Ejes 1 y 2 — pipeline animado, y el replay del scrubber con campo libre
3. Eje 3 — gobernanza, y la curva de calibración con slider
4. Eje 4a — la tarjeta, con los 3 casos reales
5. Eje 4b — ética y criterio de éxito

## Cómo se reconstruye

```bash
uv run python deck/construir.py
```

Lee `data/out/*.parquet` con **DuckDB en memoria** — nunca abre `buk.duckdb`, así que no
toma el lock ni interfiere con una corrida en paralelo. Escribe solo dentro de `deck/`.

**El build falla a propósito** si una cifra horneada no cuadra con los artefactos:
alertas/mes del canal conversación, activos del último mes, garantía de ≥2 dimensiones,
versión del catálogo y los 3 casos de tarjeta. El deck no puede desviarse de los datos sin
que alguien se entere primero.

Las curvas de `REGLAS.md` viajan como constantes citando su sección: el markdown
autogenerado es frágil de parsear y esas cifras están congeladas.

## Capturas de respaldo

Deja PNG/JPG en `deck/capturas/` y vuelve a correr `construir.py`: quedan embebidos en
base64 dentro del HTML y se ven con `C`. Si la carpeta está vacía el deck lo dice en
pantalla en vez de mostrar imágenes rotas.

Conviene tener tres: la consola de BigQuery con la consulta corrida, el Google Sheet de la
bitácora, y la tarjeta real en Google Chat.

## Una cosa que conviene saber antes de presentar

El scrubber **sobre-redacta**: «del» es un token del directorio, porque aparece en nombres
compuestos, y el regex lo reemplaza en cualquier contexto. Son 52 casos en las 31 notas
cacheadas y **se ven en rojo en la slide 2, a propósito**.

Está construido como beat del guion, no escondido: sobre-redactar es el error en la
dirección segura, y es exactamente el argumento de por qué en producción esto es Cloud DLP
y no una lista de regex propia. Si prefieres esconderlo, el arreglo es cambiar la constante
`REPLAY` en la plantilla por notas sin falsos positivos (índices 1, 20 o 28) — pero pierdes
el mejor momento de honestidad técnica del deck.
