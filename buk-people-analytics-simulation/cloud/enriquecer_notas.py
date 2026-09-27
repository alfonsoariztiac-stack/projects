"""
Fase 4/5 del Job: las notas de bitácora pasan por el LLM y aterrizan en la
tabla `bitacora_llm`.

Esta fase existe para cerrar un circuito que hasta ahora quedaba abierto:
`leer_docs.py` y `evaluar.py` procesaban notas y las imprimían, pero el
resultado no llegaba a ninguna parte. Acá el análisis se persiste, y
`chat_card.py` lo lee al construir la tarjeta.

Dos decisiones de diseño que se defienden en la sala:

1. **Tabla propia, no una columna de `employee_360`.** El sentimiento no entra
   a la tabla que las reglas leen. Por eso ninguna regla puede referenciarlo:
   no es una prohibición declarada, es que la columna no existe donde el motor
   mira. La promesa "el texto no gatilla ninguna alerta" pasa de ser una
   política a ser una imposibilidad estructural. El contexto cualitativo se
   engancha aguas abajo de la decisión, en la entrega.

2. **Corre DESPUÉS de decidir, no antes.** Esta fase va detrás de `pipeline`
   en el Job, y solo procesa las notas de las personas que efectivamente van a
   recibir una tarjeta este mes. Es minimización de datos, no solo
   anonimización: el texto de las ~2.000 personas sobre las que no vamos a
   actuar nunca sale del perímetro, ni siquiera redactado. Y refuerza la
   tesis del eje: el modelo lee después de que la alerta ya se decidió con
   datos duros, así que no pudo haber influido en la decisión ni aunque
   quisiera.

3. **Incremental por hash de la nota redactada.** Antes de llamar al modelo se
   redacta localmente (determinista, sin red) y se hace anti-join contra los
   `hash_nota` que ya están en la tabla. Una corrida mensual procesa las notas
   nuevas del mes; volver a correr el mismo mes procesa cero. Reprocesar no
   vuelve a mandar el texto a un tercero ni a pagar el token, que es la
   propiedad que uno quiere de un job que se puede reintentar.

Lo que NO se escribe nunca: el texto original de la nota. La tabla guarda la
salida del modelo, las citas (que son del texto YA redactado) y la
trazabilidad que arma `provider.procesar_nota()`. El vínculo con la persona lo
pone la clave de la fila que vino de `stg_bitacora`, no la salida del modelo —
el modelo nunca supo de quién hablaba.

Uso:
    uv run --project cloud python cloud/enriquecer_notas.py
    uv run --project cloud python cloud/enriquecer_notas.py --todos-los-periodos
    uv run --project cloud python cloud/enriquecer_notas.py --max-notas 50
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import warnings

import pandas as pd
import yaml
from google.cloud import bigquery

import config

# Mismo motivo que en cargar_bq.py / pipeline.py: la advertencia sobre
# pandas-gbq no aporta nada en una corrida que se muestra en pantalla.
warnings.filterwarnings("ignore", message=".*pandas-gbq.*", category=FutureWarning)

# El SDK de google-genai emite una recomendación sobre "automatic function
# calling" en cada import, irrelevante acá (no usamos function calling) y que
# ensucia el log de la corrida, que es material de la demo.
logging.getLogger("google_genai.models").setLevel(logging.ERROR)

config.usar_src()
sys.path.insert(0, str(config.SRC / "llm"))
import provider  # noqa: E402
from scrubber import redactar  # noqa: E402

TABLA = "bitacora_llm"
CATALOGO = config.SRC / "rules" / "reglas.yaml"

# El mismo canal que `chat_card.py`: solo la conversación llega como tarjeta,
# así que solo ahí tiene sentido enriquecer con contexto cualitativo. Los
# canales de panel se revisan en ciclo, con la persona delante.
CANAL_TARJETA = "conversacion"

# Tope duro por corrida. Un job que se cuelga llamando a un LLM 9.250 veces no
# es una feature, es un incidente: el límite se declara acá y se ve en el log.
MAX_NOTAS = 400

DESCRIPCION = (
    "Lectura del LLM sobre las notas de bitácora: sentimiento, temas y citas "
    "del texto YA redactado por el scrubber. Contexto de entrega, no insumo "
    "de reglas — ninguna columna de esta tabla entra a employee_360."
)

ESQUEMA = [
    bigquery.SchemaField("employee_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("fecha", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("idx_mes", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("periodo", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("tipo_instancia", "STRING",
                         description="instancia de la que salió la nota"),
    bigquery.SchemaField("sentimiento", "STRING", mode="REQUIRED",
                         description="valores: positivo, neutro, negativo, "
                                     "insuficiente, no_procesado"),
    bigquery.SchemaField("temas", "STRING", mode="REPEATED",
                         description="máx. 3, del enum cerrado de schema.py"),
    bigquery.SchemaField("senales", "STRING", mode="REPEATED",
                         description="subconjunto de temas en tono negativo"),
    bigquery.SchemaField("citas", "STRING", mode="REPEATED",
                         description="textuales del texto REDACTADO, verificadas"),
    bigquery.SchemaField("confianza", "FLOAT"),
    bigquery.SchemaField("hash_nota", "STRING", mode="REQUIRED",
                         description="sha256 del texto redactado · clave de idempotencia"),
    bigquery.SchemaField("modelo", "STRING"),
    bigquery.SchemaField("version_prompt", "STRING"),
    bigquery.SchemaField("procesado_en", "TIMESTAMP"),
]


def _idx_mes(fecha) -> int:
    """Misma aritmética que `warehouse.dim_periodos()` y que los .sql."""
    return fecha.year * 12 + fecha.month - 1


def _periodo(fecha) -> str:
    return f"{fecha.year:04d}-{fecha.month:02d}"


def _ventana_meses() -> int:
    """`contexto_cualitativo.ventana_meses` del catálogo, no un número acá.

    Qué tan atrás sigue siendo "contexto de esta conversación" es una decisión
    de negocio, y las decisiones de negocio viven en `reglas.yaml`. Este
    módulo la obedece.
    """
    cat = yaml.safe_load(CATALOGO.read_text(encoding="utf-8"))
    return int((cat.get("contexto_cualitativo") or {}).get("ventana_meses", 6))


def _notas_candidatas(cli: bigquery.Client, ventana: int,
                      solo_ultimo_periodo: bool = True) -> pd.DataFrame:
    """Notas de bitácora de quienes van a recibir tarjeta, dentro de la ventana.

    El universo NO son todas las notas del mes: son las notas de las personas
    que ya quedaron en `alertas` para el canal de conversación. Mandar al
    modelo el texto de alguien sobre quien no vamos a actuar sería recolectar
    por si acaso.

    `solo_ultimo_periodo` es el modo de producción (las alertas de este mes);
    apagarlo hace el backfill histórico completo, que es una operación de
    puesta en marcha, no de corrida mensual.
    """
    filtro_periodo = (
        f"AND a.periodo = (SELECT MAX(periodo) FROM `{config.DATASET_ID}.alertas` "
        f"WHERE canal = '{CANAL_TARJETA}')" if solo_ultimo_periodo else ""
    )
    sql = f"""
    WITH objetivo AS (
      SELECT a.employee_id, MAX(a.idx_mes) AS idx_alerta
      FROM `{config.DATASET_ID}.alertas` a
      WHERE a.canal = '{CANAL_TARJETA}' {filtro_periodo}
      GROUP BY a.employee_id
    )
    SELECT b.employee_id, b.fecha, b.tipo_instancia, b.nota
    FROM `{config.DATASET_ID}.stg_bitacora` b
    JOIN objetivo o USING (employee_id)
    WHERE EXTRACT(YEAR FROM b.fecha) * 12 + EXTRACT(MONTH FROM b.fecha) - 1
            <= o.idx_alerta
      AND EXTRACT(YEAR FROM b.fecha) * 12 + EXTRACT(MONTH FROM b.fecha) - 1
            > o.idx_alerta - {int(ventana)}
    ORDER BY b.fecha, b.employee_id
    """
    return cli.query(sql, location=config.REGION).to_dataframe(
        create_bqstorage_client=False)


def _hashes_ya_procesados(cli: bigquery.Client) -> set[str]:
    """Los `hash_nota` que ya están en la tabla. Set vacío si aún no existe."""
    try:
        df = cli.query(
            f"SELECT DISTINCT hash_nota FROM `{config.DATASET_ID}.{TABLA}`",
            location=config.REGION,
        ).to_dataframe(create_bqstorage_client=False)
    except Exception:
        return set()
    return set(df["hash_nota"])


# Cuántos fallos de red seguidos hacen abandonar la fase. Un corte puntual
# —`Connection reset by peer` a mitad de una tanda— no debe costar las 90
# llamadas que ya se hicieron; una red caída sí debe terminar rápido.
REINTENTOS_RED = 3
ERRORES_SEGUIDOS_MAX = 5


def _procesar_con_reintento(texto: str, usar_cache: bool) -> dict:
    """`provider.procesar_nota()` con reintento ante error de transporte.

    `provider` ya reintenta una vez cuando la respuesta no valida contra el
    esquema; lo que no cubre es que la conexión se caiga antes de haber
    respuesta. Eso se reintenta acá, con espera creciente, porque es la clase
    de fallo que se resuelve solo.
    """
    for intento in range(REINTENTOS_RED):
        try:
            return provider.procesar_nota(texto, usar_cache=usar_cache)
        except RuntimeError:
            # Falta de credencial: no se reintenta, no se va a arreglar solo.
            raise
        except Exception:
            if intento == REINTENTOS_RED - 1:
                raise
            time.sleep(2 * (intento + 1))
    raise AssertionError("inalcanzable")


def _fila(nota: pd.Series, envoltorio: dict) -> dict:
    return {
        "employee_id": nota["employee_id"],
        "fecha": nota["fecha"],
        "idx_mes": _idx_mes(nota["fecha"]),
        "periodo": _periodo(nota["fecha"]),
        "tipo_instancia": nota.get("tipo_instancia"),
        "sentimiento": envoltorio.get("sentimiento", "no_procesado"),
        "temas": list(envoltorio.get("temas") or []),
        "senales": list(envoltorio.get("senales") or []),
        "citas": list(envoltorio.get("citas_respaldo") or []),
        "confianza": float(envoltorio.get("confianza") or 0.0),
        "hash_nota": envoltorio["hash_nota"],
        "modelo": envoltorio.get("modelo"),
        "version_prompt": envoltorio.get("version_prompt"),
        "procesado_en": envoltorio.get("procesado_en"),
    }


def _escribir(cli: bigquery.Client, filas: list[dict]) -> None:
    df = pd.DataFrame(filas, columns=[c.name for c in ESQUEMA])
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.date
    df["procesado_en"] = pd.to_datetime(df["procesado_en"], utc=True, format="ISO8601")
    destino = f"{config.DATASET_ID}.{TABLA}"
    cfg = bigquery.LoadJobConfig(
        schema=ESQUEMA,
        # APPEND y no TRUNCATE: la deduplicación la garantiza el anti-join por
        # hash, y así una corrida que falla a mitad no borra el histórico.
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        destination_table_description=DESCRIPCION,
    )
    cli.load_table_from_dataframe(df, destino, job_config=cfg).result()


def construir(cli: bigquery.Client, solo_ultimo_periodo: bool = True,
              max_notas: int = MAX_NOTAS, usar_cache: bool = True,
              verboso: bool = True) -> dict[str, int]:
    ventana = _ventana_meses()
    notas = _notas_candidatas(cli, ventana, solo_ultimo_periodo)
    ya = _hashes_ya_procesados(cli)

    # Redactar acá, antes de decidir: el hash de la caché y el de la tabla es
    # el del texto redactado, así que hay que redactar para saber si falta.
    # Es determinista y no sale a la red — `procesar_nota()` volverá a
    # redactar el mismo texto y obtendrá el mismo hash.
    notas = notas.assign(
        hash_nota=[provider._hash(redactar(t)) for t in notas["nota"]]
    )
    unicas = notas.drop_duplicates("hash_nota")
    faltantes = unicas[~unicas["hash_nota"].isin(ya)]
    n_ya = len(unicas) - len(faltantes)
    truncado = len(faltantes) > max_notas
    pendientes = faltantes.head(max_notas)

    filas, n_cache, n_llamadas, n_fallidas, n_error = [], 0, 0, 0, 0
    sin_credencial, corte_red, seguidos = None, None, 0
    for _, nota in pendientes.iterrows():
        en_cache = provider._leer_cache(nota["hash_nota"]) is not None
        try:
            envoltorio = _procesar_con_reintento(nota["nota"], usar_cache)
        except RuntimeError as e:
            # El adaptador no tiene con qué hablar con el modelo (sin
            # GEMINI_API_KEY, o backend=vertex sin permisos). Esta fase se
            # detiene, pero el JOB NO: el contexto cualitativo es opcional
            # por diseño —la tarjeta se construye igual sin él— y una alerta
            # que ya se decidió con datos duros no debe dejar de enviarse
            # porque el enriquecimiento no estaba disponible. Se declara
            # ruidosamente en el log, no en silencio.
            sin_credencial = str(e)
            break
        except Exception as e:
            # La nota queda sin procesar y se reintentará en la próxima
            # corrida: el anti-join por hash hace que eso no cueste nada.
            n_error += 1
            seguidos += 1
            if seguidos >= ERRORES_SEGUIDOS_MAX:
                corte_red = f"{type(e).__name__}: {e}"
                break
            continue
        seguidos = 0
        n_cache += en_cache
        n_llamadas += not en_cache
        n_fallidas += envoltorio.get("sentimiento") == "no_procesado"
        filas.append(_fila(nota, envoltorio))

    # Se escribe siempre lo que alcanzó a procesarse, incluso si la fase se
    # cortó: el avance parcial es válido y la próxima corrida retoma donde
    # quedó, porque la idempotencia es por hash de nota, no por corrida.
    if filas:
        _escribir(cli, filas)

    if verboso:
        alcance = ("alertas del último período" if solo_ultimo_periodo
                   else "todos los períodos (backfill)")
        print(f"Alcance: {alcance} · canal {CANAL_TARJETA} · ventana {ventana} meses")
        print(f"   personas a enriquecer  {notas['employee_id'].nunique():>7,}")
        print(f"   notas en ventana       {len(unicas):>7,}")
        print(f"   ya en {TABLA:<16} {n_ya:>7,}")
        print(f"   nuevas procesadas      {len(filas):>7,} "
              f"({n_cache:,} desde caché · {n_llamadas:,} llamadas al modelo)")
        print(f"   no_procesado           {n_fallidas:>7,}")
        if n_error:
            print(f"   error de red           {n_error:>7,} "
                  f"(quedan para la próxima corrida)")
        if corte_red:
            print(f" ! {ERRORES_SEGUIDOS_MAX} fallos de red seguidos ({corte_red}) — "
                  f"fase cortada, el job continúa")
        if truncado:
            print(f" ! tope de {max_notas:,} notas por corrida alcanzado — "
                  f"quedan pendientes para la próxima")
        if sin_credencial:
            print(f" ! sin acceso al modelo ({sin_credencial}) — fase detenida, "
                  f"el job continúa: el contexto cualitativo es opcional")
        print(f"Contexto cualitativo: tabla `{TABLA}` en {config.DATASET_ID}")

    return {"candidatas": len(unicas), "nuevas": len(filas),
            "cache": n_cache, "llamadas": n_llamadas, "no_procesado": n_fallidas,
            "error_red": n_error, "sin_credencial": bool(sin_credencial)}


def main(solo_ultimo_periodo: bool = True, max_notas: int = MAX_NOTAS,
         usar_cache: bool = True, impersonar: bool = False,
         verboso: bool = True) -> dict[str, int]:
    cli = config.cliente(impersonar=impersonar)
    if verboso:
        print(f"Identidad: {config.quien(cli)}")
        print(f"Modelo: {provider.MODELO} · backend {provider.BACKEND} · "
              f"prompt {provider.VERSION_PROMPT}")
    return construir(cli, solo_ultimo_periodo, max_notas, usar_cache, verboso)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--todos-los-periodos", action="store_true",
                    help="backfill histórico en vez de solo las alertas del último mes")
    ap.add_argument("--max-notas", type=int, default=MAX_NOTAS,
                    help="tope duro de notas nuevas por corrida")
    ap.add_argument("--sin-cache", action="store_true",
                    help="ignorar data/cache/llm/ y llamar al modelo de verdad")
    ap.add_argument("--impersonar", action="store_true")
    args = ap.parse_args()
    main(solo_ultimo_periodo=not args.todos_los_periodos, max_notas=args.max_notas,
         usar_cache=not args.sin_cache, impersonar=args.impersonar)
