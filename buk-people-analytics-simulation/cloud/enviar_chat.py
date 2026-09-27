"""
Variante de F4: postea al Space real las mismas 3 tarjetas del canal
`conversacion`, leyéndolas desde la tabla `alertas` de BigQuery en vez de
`data/out/alertas.parquet`.

`src/deliver/chat_card.py` no se toca ni una línea: `construir_tarjeta()`,
`enviar()` y `renderizar_html()` se reusan tal cual. Lo único nuevo acá es el
origen del dato — `_cargar_alertas()` y `_cargar_nombres()` son la misma
consulta que hacía `chat_card.py`, pero contra `alertas` y `stg_directorio` en
BigQuery en vez de Parquet/CSV local.

`_cargar_contexto_llm()` es lo único que no tiene equivalente local: trae de
`bitacora_llm` (la tabla que escribe `enriquecer_notas.py`) la lectura del LLM
más reciente de cada persona y se la pasa a `construir_tarjeta()`. Es el
enganche del Eje 2 con la tarjeta, y ocurre acá —en la entrega— y no en el
warehouse: `employee_360` no tiene ninguna de esas columnas, así que ninguna
regla pudo haberlas mirado.

Uso:
    uv run --project cloud python cloud/enviar_chat.py
    uv run --project cloud python cloud/enviar_chat.py --enviar
    uv run --project cloud python cloud/enviar_chat.py --impersonar --enviar
"""

from __future__ import annotations

import argparse
import sys
import warnings

import pandas as pd
from google.cloud import bigquery

import config

# Mismo motivo que en cargar_bq.py / pipeline.py: la advertencia sobre
# pandas-gbq no aporta nada en una corrida que se muestra en pantalla.
warnings.filterwarnings("ignore", message=".*pandas-gbq.*", category=FutureWarning)

config.usar_src()
sys.path.insert(0, str(config.SRC / "deliver"))
import chat_card  # noqa: E402

CANAL_TARJETA = chat_card.CANAL_TARJETA


def _cargar_alertas(cli: bigquery.Client) -> pd.DataFrame:
    """Variante del filtro de `chat_card._cargar_alertas()`: incluye
    `lista_seguimiento` además de `notificada`.

    `conversacion` tiene cupo_mensual compartido entre R01/R03/R04 por
    prioridad (reglas.yaml). R01 y R03 agotan el cupo casi todos los meses,
    así que R04 rara vez gana un puesto — su última fila `notificada` puede
    quedar meses atrás aunque el motor la siga evaluando como candidata cada
    corte. Para la demo (mostrar la tarjeta que generaría cada regla, no el
    historial de qué ganó cupo) conviene el candidato vigente más reciente,
    no el último que efectivamente salió por Chat.
    """
    return cli.query(
        f"SELECT * FROM `{config.DATASET_ID}.alertas` "
        f"WHERE estado IN ('notificada', 'lista_seguimiento') "
        f"AND canal = '{CANAL_TARJETA}'",
        location=config.REGION,
    ).to_dataframe(create_bqstorage_client=False)


def _cargar_contexto_llm(cli: bigquery.Client) -> dict[tuple[str, str], dict]:
    """La lectura del LLM más reciente por persona, indexada por (id, periodo).

    Se resuelve con una consulta y no en pandas porque la ventana la define el
    catálogo (`contexto_cualitativo.ventana_meses`) y conviene que el recorte
    viva junto al dato. Por cada mes de alerta se toma la última nota leída
    dentro de la ventana hacia atrás: la tarjeta de agosto no puede mostrar
    una nota de septiembre que en su momento no existía.

    Devuelve `{}` si `bitacora_llm` todavía no existe — la tarjeta se
    construye igual, solo sin la sección de contexto.
    """
    ventana = _ventana_meses()
    sql = f"""
    WITH pares AS (
      SELECT DISTINCT employee_id, periodo, idx_mes
      FROM `{config.DATASET_ID}.alertas`
      WHERE canal = '{CANAL_TARJETA}'
    ),
    emparejado AS (
      SELECT
        p.employee_id, p.periodo AS periodo_alerta,
        b.periodo AS periodo_nota, b.sentimiento, b.temas, b.citas, b.idx_mes,
        ROW_NUMBER() OVER (
          PARTITION BY p.employee_id, p.periodo ORDER BY b.idx_mes DESC
        ) AS rn
      FROM pares p
      JOIN `{config.DATASET_ID}.bitacora_llm` b
        ON b.employee_id = p.employee_id
       AND b.idx_mes <= p.idx_mes
       AND b.idx_mes > p.idx_mes - {ventana}
    )
    SELECT employee_id, periodo_alerta, periodo_nota, sentimiento, temas, citas
    FROM emparejado WHERE rn = 1
    """
    try:
        df = cli.query(sql, location=config.REGION).to_dataframe(
            create_bqstorage_client=False)
    except Exception as e:
        print(f"  (sin contexto cualitativo: {type(e).__name__} — la tarjeta se "
              f"construye sin esa sección)")
        return {}

    return {
        (f.employee_id, f.periodo_alerta): {
            "periodo": f.periodo_nota,
            "sentimiento": f.sentimiento,
            # `or []` no sirve: los ARRAY de BigQuery llegan como ndarray y
            # su valor de verdad es ambiguo. list() sobre el ndarray basta.
            "temas": list(f.temas) if f.temas is not None else [],
            "citas": list(f.citas) if f.citas is not None else [],
        }
        for f in df.itertuples()
    }


def _ventana_meses() -> int:
    """`contexto_cualitativo.ventana_meses` del catálogo, con default conservador."""
    return int((chat_card._contexto_cualitativo() or {}).get("ventana_meses", 6))


def _cargar_nombres(cli: bigquery.Client) -> dict[str, str]:
    df = cli.query(
        f"SELECT employee_id, nombre FROM `{config.DATASET_ID}.stg_directorio`",
        location=config.REGION,
    ).to_dataframe(create_bqstorage_client=False)
    return dict(zip(df.employee_id, df.nombre))


def casos_demo(cli: bigquery.Client, n_por_regla: int = 1) -> list[dict]:
    """Réplica de `chat_card.casos_demo()`: el caso notificado más reciente de
    cada regla del canal `conversacion`, leído desde BigQuery."""
    df = _cargar_alertas(cli)
    nombres = _cargar_nombres(cli)
    # A igual período, prioriza notificada sobre lista_seguimiento: si la
    # regla sí ganó cupo ese mes, es ese caso el que corresponde mostrar.
    orden_estado = {"notificada": 0, "lista_seguimiento": 1}
    df = df.assign(_orden_estado=df["estado"].map(orden_estado))
    casos = []
    for _, grupo in df.sort_values(
        ["periodo", "_orden_estado"], ascending=[False, True]
    ).groupby("regla"):
        for _, fila in grupo.head(n_por_regla).iterrows():
            caso = fila.drop("_orden_estado").to_dict()
            caso["nombre"] = nombres.get(caso["employee_id"], caso["employee_id"])
            casos.append(caso)
    casos.sort(key=lambda c: c["regla"])
    return casos


def main(n_por_regla: int = 1, en_vivo: bool = False, impersonar: bool = False) -> None:
    cli = config.cliente(impersonar=impersonar)
    print(f"Identidad: {config.quien(cli)}")

    casos = casos_demo(cli, n_por_regla=n_por_regla)
    contextos = _cargar_contexto_llm(cli)
    con_contexto = sum(1 for c in casos if (c["employee_id"], c["periodo"]) in contextos)
    print(f"{len(casos)} caso(s) real(es) de {config.DATASET_ID}.alertas (canal {CANAL_TARJETA})"
          f" · {con_contexto} con contexto cualitativo\n")
    for caso in casos:
        contexto = contextos.get((caso["employee_id"], caso["periodo"]))
        tarjeta = chat_card.construir_tarjeta(caso, contexto)
        ruta_html = chat_card.renderizar_html(caso, contexto)
        estado = "offline (usar --enviar para postear al webhook)"
        if en_vivo:
            estado = "✓ enviada a Chat" if chat_card.enviar(tarjeta) else "✗ falló el webhook, ver HTML"
        print(f"[{caso['regla']}] {caso['employee_id']} ({caso['nombre']}) → "
              f"{estado} · {ruta_html.relative_to(config.RAIZ)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-por-regla", type=int, default=1,
                     help="cuántos casos tomar por regla del canal conversación")
    ap.add_argument("--enviar", action="store_true",
                     help="postear de verdad al GOOGLE_CHAT_WEBHOOK (si no, solo genera el HTML)")
    ap.add_argument("--impersonar", action="store_true",
                     help="correr como la service account en vez de con tu ADC")
    args = ap.parse_args()
    main(n_por_regla=args.n_por_regla, en_vivo=args.enviar, impersonar=args.impersonar)
