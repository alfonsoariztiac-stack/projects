"""
Eje 4: la alerta que de verdad llega al Happiness Manager.

Este módulo no inventa contenido nuevo: arma la tarjeta a partir de columnas
que `motor.py` ya calculó (`senales`, `evidencia`, `accion_sugerida`,
`lectura`, `meses_sin_nota`). Si algo no está en `reglas.yaml`, no aparece en
la tarjeta — la misma disciplina del eje 3 aplicada a la entrega.

Reglas de diseño no negociables (ver `REGLAS.md` y el plan del caso):
- Solo canal `conversacion` llega como tarjeta de Chat. `compensaciones` es un
  panel, no una alerta a una persona — no le corresponde esta forma.
- Nunca un score numérico ni la frase "riesgo de fuga" en el encabezado.
- Toda señal trae su dato de respaldo y el período al que corresponde.
- Sección "Qué no sabemos" es obligatoria: declarar los puntos ciegos evita
  que el HRBP lea la tarjeta como veredicto en vez de como hipótesis.
- El contexto cualitativo (lo que el LLM leyó en la bitácora) va DESPUÉS de
  "Señales detectadas" y en su propia sección, nunca entre las señales. La
  posición es el argumento: no gatilló la alerta y no debe leerse como si lo
  hubiera hecho. Qué se muestra y con qué texto lo declara el bloque
  `contexto_cualitativo` de `reglas.yaml`, no este archivo.
- El nombre se usa aquí solo para dirigirse a la persona correcta al mostrar
  el resultado de una regla ya evaluada — nunca como insumo de una condición
  (`reglas.yaml` prohíbe explícitamente `nombre` como atributo de regla).

Los tres botones no ejecutan nada en la demo: no hay un backend de Chat app
detrás de un webhook entrante, solo un endpoint de salida. Abren un correo
pre-armado a People Analytics con la decisión ya redactada. En producción esto
sería una escritura directa a la hoja de seguimiento vía la Chat API con una
Chat app real. Se declara así en vez de simular un clic que no hace nada.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys
import urllib.parse

import duckdb
import pandas as pd
import requests
from dotenv import load_dotenv

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from ingest import CRUDO, RAIZ, SALIDA  # noqa: E402

load_dotenv(RAIZ / ".env")

CATALOGO = RAIZ / "src" / "rules" / "reglas.yaml"


def _contexto_cualitativo() -> dict:
    """El bloque `contexto_cualitativo` de `reglas.yaml`, tal cual.

    Se lee el catálogo directo y no vía `motor.py` a propósito: la entrega no
    necesita el motor de reglas, solo el permiso escrito de qué puede mostrar.
    Si el bloque no existe o está deshabilitado, la sección no se dibuja.
    """
    cat = yaml.safe_load(CATALOGO.read_text(encoding="utf-8"))
    ctx = cat.get("contexto_cualitativo") or {}
    return ctx if ctx.get("habilitado") else {}

ALERTAS = SALIDA / "alertas.parquet"
DIRECTORIO = CRUDO / "bq_directorio_personas.csv"
SALIDA_HTML = SALIDA / "alertas_demo"
WEBHOOK = os.environ.get("GOOGLE_CHAT_WEBHOOK")
CORREO_REGISTRO = "registro-alertas@buk.example"

CANAL_TARJETA = "conversacion"

NOTA_BOTONES = (
    "Estos botones abren un correo pre-armado a People Analytics con la "
    "decisión — en esta demo no hay una Chat app con backend detrás del "
    "webhook. En producción, el mismo clic escribe directo en la hoja de "
    "seguimiento vía la Chat API."
)

PIE = (
    "Esta alerta es una hipótesis basada en datos, no una evaluación de la "
    "persona. Expira en 30 días. No forma parte de su expediente."
)


def _cargar_alertas() -> pd.DataFrame:
    """Lee `alertas.parquet` directo, sin abrir `buk.duckdb` (Bloque 2 congelado)."""
    with duckdb.connect() as con:
        return con.execute(
            f"SELECT * FROM read_parquet('{ALERTAS.as_posix()}') "
            f"WHERE estado = 'notificada' AND canal = '{CANAL_TARJETA}'"
        ).fetchdf()


def _cargar_nombres() -> dict[str, str]:
    dirario = pd.read_csv(DIRECTORIO, usecols=["employee_id", "nombre"])
    return dict(zip(dirario.employee_id, dirario.nombre))


def casos_demo(n_por_regla: int = 1) -> list[dict]:
    """El caso notificado más reciente de cada regla del canal `conversacion`.

    Una regla por caso, no una regla repetida tres veces: el objetivo de la
    demo es mostrar que la tarjeta se adapta a la evidencia que la gatilló,
    no encontrar los tres ejemplos más extremos.
    """
    df = _cargar_alertas()
    nombres = _cargar_nombres()
    casos = []
    for _, grupo in df.sort_values("periodo", ascending=False).groupby("regla"):
        for _, fila in grupo.head(n_por_regla).iterrows():
            caso = fila.to_dict()
            caso["nombre"] = nombres.get(caso["employee_id"], caso["employee_id"])
            casos.append(caso)
    casos.sort(key=lambda c: c["regla"])
    return casos


TONO = {
    "positivo": "tono positivo",
    "neutro": "tono neutro",
    "negativo": "tono negativo",
}

# Dos respuestas que el pipeline devuelve a propósito y que NO son una lectura:
# `insuficiente` la declara el propio modelo cuando el texto no da evidencia,
# `no_procesado` la pone `provider.py` cuando la respuesta no validó ni al
# reintento. Ninguna de las dos se muestra como si fuera un tono — se declaran
# como vacío, en "Qué no sabemos".
SIN_LECTURA = {"insuficiente", "no_procesado"}


def _hay_contexto(contexto: dict | None) -> bool:
    return bool(contexto) and contexto.get("sentimiento") not in SIN_LECTURA


def _contexto_widgets(contexto: dict | None, ctx: dict) -> list[dict]:
    """Widgets de la sección cualitativa, recortados a lo que el catálogo permite.

    `campos_visibles`, `max_temas` y `max_citas` salen de `reglas.yaml`: si un
    campo no está declarado ahí, no se dibuja aunque venga en el dato. Misma
    disciplina que `accion_sugerida` — la tarjeta no muestra nada que el
    catálogo no autorice.
    """
    if not ctx or not _hay_contexto(contexto):
        return []

    visibles = set(ctx.get("campos_visibles") or [])
    widgets = []

    if "sentimiento" in visibles:
        temas = list(contexto.get("temas") or [])[: ctx.get("max_temas", 2)]
        decorado = {
            "topLabel": f"Última nota registrada · {contexto.get('periodo', '—')}",
            "text": TONO.get(contexto["sentimiento"], contexto["sentimiento"]),
        }
        if temas and "temas" in visibles:
            decorado["bottomLabel"] = "temas: " + ", ".join(temas)
        widgets.append({"decoratedText": decorado})

    if "cita" in visibles:
        for cita in list(contexto.get("citas") or [])[: ctx.get("max_citas", 1)]:
            widgets.append({"textParagraph": {"text": f"<i>«{cita}»</i>"}})

    if widgets:
        widgets.append({"textParagraph": {"text": ctx["descargo"].strip()}})
    return widgets


def _que_no_sabemos(caso: dict, contexto: dict | None = None) -> list[str]:
    """Puntos ciegos declarados a partir de lo que el dato NO cubre.

    No es una lista fija: se arma según qué falte en este caso puntual. Un
    caso con historial corto y otro con bitácora al día no comparten los
    mismos vacíos.
    """
    puntos = []
    meses_sin_nota = caso.get("meses_sin_nota")
    if pd.notna(meses_sin_nota) and meses_sin_nota >= 3:
        puntos.append(
            f"Sin registros en su bitácora hace {int(meses_sin_nota)} meses: "
            "el contexto cualitativo puede estar desactualizado."
        )
    elif not _hay_contexto(contexto):
        # Hay notas recientes pero no hay lectura utilizable: o el modelo
        # declaró que el texto no daba evidencia, o la respuesta no validó.
        # Se dice, en vez de dejar la sección vacía y que parezca que no
        # había nada que decir.
        puntos.append(
            "Hay notas recientes en su bitácora, pero sin una lectura "
            "cualitativa concluyente: no la uses como respaldo."
        )
    if pd.isna(caso.get("csat_delta_3m")):
        puntos.append(
            "Sin CSAT: su rol no es de cara al cliente, no hay señal de "
            "satisfacción de cliente que contrastar."
        )
    if pd.isna(caso.get("prod_delta_3m")):
        puntos.append("Sin métricas operativas registradas para este rol.")
    antiguedad = caso.get("antiguedad_meses")
    if pd.notna(antiguedad) and antiguedad < 12:
        puntos.append(
            f"Lleva {int(antiguedad)} meses en Buk: historial todavía corto "
            "para separar una tendencia real de ruido de arranque."
        )
    if not puntos:
        puntos.append("Sin vacíos relevantes detectados en las fuentes disponibles.")
    return puntos


def _acciones(caso: dict) -> list[str]:
    """`accion_sugerida` tal cual está en `reglas.yaml`, partida en oraciones.

    No se agrega ninguna acción que no venga del catálogo: si el YAML trae
    una sola oración, la tarjeta muestra una sola acción.
    """
    texto = caso["accion_sugerida"].strip()
    oraciones = [o.strip() for o in re.split(r"(?<=[.:])\s+", texto) if o.strip()]
    return oraciones


def _mailto(caso: dict, decision: str) -> str:
    asunto = f"Alerta {caso['employee_id']} ({caso['regla']}) — {decision}"
    cuerpo = (
        f"Persona: {caso['nombre']} ({caso['employee_id']})\n"
        f"Regla: {caso['regla']} — {caso['regla_nombre']}\n"
        f"Período de la alerta: {caso['periodo']}\n"
        f"Decisión: {decision}\n\n"
        "Comentario (opcional):\n"
    )
    qs = urllib.parse.urlencode({"subject": asunto, "body": cuerpo}, quote_via=urllib.parse.quote)
    return f"mailto:{CORREO_REGISTRO}?{qs}"


def construir_tarjeta(caso: dict, contexto: dict | None = None) -> dict:
    """Arma el JSON de Google Chat Cards v2 para un caso ya evaluado por el motor.

    `contexto` es la lectura del LLM sobre la última nota de bitácora de esta
    persona (`bitacora_llm`), o `None`. Llega como argumento y no se busca
    aquí adentro justamente porque es opcional: la tarjeta se construye
    exactamente igual sin él, y ninguna decisión de la alerta depende de que
    exista.
    """
    subtitulo = (
        f"{caso['area']} · {caso['job_family']} · {caso['etiqueta_nivel']} · "
        f"{int(caso['antiguedad_meses'])} meses en Buk"
    )

    widgets_senales = [
        {
            "decoratedText": {
                "text": evidencia,
                "topLabel": senal,
                "bottomLabel": f"corte {caso['periodo']}",
            }
        }
        for senal, evidencia in zip(caso["senales"], caso["evidencia"])
    ]

    ctx = _contexto_cualitativo()
    widgets_contexto = _contexto_widgets(contexto, ctx)

    widgets_vacios = [
        {"textParagraph": {"text": punto}}
        for punto in _que_no_sabemos(caso, contexto)
    ]

    widgets_acciones = [
        {"textParagraph": {"text": accion}} for accion in _acciones(caso)
    ]

    sections = [
        {"header": "Por qué te lo mostramos", "widgets": [{"textParagraph": {"text": caso["lectura"]}}]},
        {"header": "Señales detectadas", "widgets": widgets_senales},
    ]
    # Después de las señales y antes de los vacíos: es contexto de la
    # conversación, no evidencia de la alerta.
    if widgets_contexto:
        sections.append({"header": ctx["encabezado"], "widgets": widgets_contexto})
    sections += [
        {"header": "Qué no sabemos", "widgets": widgets_vacios},
        {"header": "Qué sugerimos", "widgets": widgets_acciones},
        {
            "widgets": [
                {
                    "buttonList": {
                        "buttons": [
                            {"text": "Agendar conversación",
                             "onClick": {"openLink": {"url": _mailto(caso, "Agendar conversación")}}},
                            {"text": "Ya lo estoy abordando",
                             "onClick": {"openLink": {"url": _mailto(caso, "Ya lo estoy abordando")}}},
                            {"text": "Descartar — no aplica",
                             "onClick": {"openLink": {"url": _mailto(caso, "Descartar — no aplica")}}},
                        ]
                    }
                },
                {"textParagraph": {"text": NOTA_BOTONES}},
            ]
        },
        {"widgets": [{"textParagraph": {"text": PIE}}]},
    ]

    return {
        "cardsV2": [
            {
                "cardId": f"alerta-{caso['employee_id']}-{caso['periodo']}",
                "card": {
                    "header": {
                        "title": f"Contexto para tu próxima conversación con {caso['nombre']}",
                        "subtitle": subtitulo,
                    },
                    "sections": sections,
                },
            }
        ]
    }


TEMPLATE_HTML = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>{{ caso.nombre }} — {{ caso.regla }}</title>
<style>
  body { font-family: -apple-system, Arial, sans-serif; background: #f1f3f4; margin: 0; padding: 32px; }
  .card { max-width: 480px; margin: auto; background: white; border-radius: 12px;
           box-shadow: 0 1px 3px rgba(0,0,0,.2); overflow: hidden; }
  .header { background: #1a73e8; color: white; padding: 16px 20px; }
  .header h1 { font-size: 16px; margin: 0 0 4px; }
  .header p { font-size: 12px; margin: 0; opacity: .9; }
  .section { padding: 12px 20px; border-bottom: 1px solid #e8eaed; }
  .section h2 { font-size: 11px; text-transform: uppercase; color: #5f6368; margin: 0 0 8px; }
  .item { margin-bottom: 8px; font-size: 13px; color: #202124; }
  .item .label { font-weight: 600; display: block; }
  .item .meta { color: #80868b; font-size: 11px; }
  .buttons { display: flex; gap: 8px; flex-wrap: wrap; }
  .buttons a { font-size: 12px; padding: 8px 12px; border: 1px solid #dadce0;
                border-radius: 6px; text-decoration: none; color: #1a73e8; }
  .nota, .pie { font-size: 11px; color: #80868b; font-style: italic; }
</style></head>
<body>
  <div class="card">
    <div class="header">
      <h1>Contexto para tu próxima conversación con {{ caso.nombre }}</h1>
      <p>{{ subtitulo }}</p>
    </div>
    <div class="section">
      <h2>Por qué te lo mostramos</h2>
      <div class="item">{{ caso.lectura }}</div>
    </div>
    <div class="section">
      <h2>Señales detectadas</h2>
      {% for senal, evidencia in zip(caso.senales, caso.evidencia) %}
      <div class="item"><span class="label">{{ senal }}</span>{{ evidencia }}
        <div class="meta">corte {{ caso.periodo }}</div></div>
      {% endfor %}
    </div>
    {% if contexto and ctx %}
    <div class="section">
      <h2>{{ ctx.encabezado }}</h2>
      <div class="item"><span class="label">Última nota registrada · {{ contexto.periodo }}</span>{{ tono }}
        {% if temas_visibles %}<div class="meta">temas: {{ temas_visibles|join(", ") }}</div>{% endif %}</div>
      {% for cita in citas_visibles %}<div class="item"><em>«{{ cita }}»</em></div>{% endfor %}
      <p class="nota">{{ ctx.descargo|trim }}</p>
    </div>
    {% endif %}
    <div class="section">
      <h2>Qué no sabemos</h2>
      {% for punto in vacios %}<div class="item">{{ punto }}</div>{% endfor %}
    </div>
    <div class="section">
      <h2>Qué sugerimos</h2>
      {% for accion in acciones %}<div class="item">{{ accion }}</div>{% endfor %}
    </div>
    <div class="section">
      <div class="buttons">
        <a href="{{ mailto_agendar }}">Agendar conversación</a>
        <a href="{{ mailto_abordando }}">Ya lo estoy abordando</a>
        <a href="{{ mailto_descartar }}">Descartar — no aplica</a>
      </div>
      <p class="nota">{{ nota_botones }}</p>
    </div>
    <div class="section" style="border-bottom: none;">
      <p class="pie">{{ pie }}</p>
    </div>
  </div>
</body></html>
"""


def renderizar_html(caso: dict, contexto: dict | None = None) -> pathlib.Path:
    """Fallback offline: la misma tarjeta, como HTML, para cuando no hay red."""
    import jinja2

    entorno = jinja2.Environment()
    entorno.globals["zip"] = zip
    ctx = _contexto_cualitativo()
    plantilla = entorno.from_string(TEMPLATE_HTML)
    html = plantilla.render(
        caso=caso,
        subtitulo=(
            f"{caso['area']} · {caso['job_family']} · {caso['etiqueta_nivel']} · "
            f"{int(caso['antiguedad_meses'])} meses en Buk"
        ),
        ctx=ctx,
        contexto=contexto if _hay_contexto(contexto) else None,
        temas_visibles=list((contexto or {}).get("temas") or [])[: ctx.get("max_temas", 2)],
        citas_visibles=list((contexto or {}).get("citas") or [])[: ctx.get("max_citas", 1)],
        tono=TONO.get((contexto or {}).get("sentimiento"), ""),
        vacios=_que_no_sabemos(caso, contexto),
        acciones=_acciones(caso),
        mailto_agendar=_mailto(caso, "Agendar conversación"),
        mailto_abordando=_mailto(caso, "Ya lo estoy abordando"),
        mailto_descartar=_mailto(caso, "Descartar — no aplica"),
        nota_botones=NOTA_BOTONES,
        pie=PIE,
    )
    SALIDA_HTML.mkdir(parents=True, exist_ok=True)
    ruta = SALIDA_HTML / f"{caso['employee_id']}_{caso['regla']}.html"
    ruta.write_text(html, encoding="utf-8")
    return ruta


def enviar(tarjeta: dict) -> bool:
    """POST al webhook real de Google Chat. `False` ante cualquier falla de red."""
    if not WEBHOOK:
        return False
    try:
        resp = requests.post(WEBHOOK, json=tarjeta, timeout=5)
        return resp.ok
    except requests.exceptions.RequestException:
        return False


def main(n_por_regla: int = 1, en_vivo: bool = False) -> None:
    casos = casos_demo(n_por_regla=n_por_regla)
    print(f"{len(casos)} caso(s) real(es) de {ALERTAS.relative_to(RAIZ)} (canal {CANAL_TARJETA})\n")
    for caso in casos:
        tarjeta = construir_tarjeta(caso)
        ruta_html = renderizar_html(caso)
        estado = "offline (usar --enviar para postear al webhook)"
        if en_vivo:
            estado = "✓ enviada a Chat" if enviar(tarjeta) else "✗ falló el webhook, ver HTML"
        print(f"[{caso['regla']}] {caso['employee_id']} ({caso['nombre']}) → "
              f"{estado} · {ruta_html.relative_to(RAIZ)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-por-regla", type=int, default=1,
                     help="cuántos casos tomar por regla del canal conversación")
    ap.add_argument("--enviar", action="store_true",
                     help="postear de verdad al GOOGLE_CHAT_WEBHOOK (si no, solo genera el HTML)")
    args = ap.parse_args()
    main(n_por_regla=args.n_por_regla, en_vivo=args.enviar)
