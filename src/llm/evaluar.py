"""
Evaluación de la capa LLM contra la verdad de laboratorio.

Mismo principio de honestidad que `src/rules/backtest.py`: `_bitacora_etiquetas.csv`
trae el tono y los temas con que el GENERADOR compuso cada nota, no una
etiqueta humana. Esto valida que la tubería completa —scrubber, prompt,
esquema, verificación de citas— reproduce una lectura razonable de un texto
que el modelo nunca vio durante su entrenamiento, no que el modelo "entienda"
bitácoras reales de Buk. Se declara antes del número, no después.

`nota <-> etiqueta` se une por POSICIÓN, no por employee_id+fecha: ambos
archivos salen de la misma columna-selección de un único DataFrame en
`generate_data.escribir()`, así que preservan el mismo orden de filas. Unir
por clave sería más "correcto" en apariencia y más frágil en los hechos: la
clave del contrato (`employee_id+fecha+autor_hrbp`) no garantiza unicidad de
`employee_id+fecha` solo, que es lo único que trae el archivo de laboratorio.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import pandas as pd

RAIZ = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "src" / "llm"))
from provider import procesar_nota  # noqa: E402

BITACORA = RAIZ / "data" / "raw" / "gs_desarrollo_bitacora.xlsx"
ETIQUETAS = RAIZ / "data" / "laboratorio" / "_bitacora_etiquetas.csv"
REPORTE = RAIZ / "data" / "out" / "reporte_llm.md"

TONO_A_SENTIMIENTO = {"pos": "positivo", "neu": "neutro", "neg": "negativo"}


def _muestra(n: int, semilla: int) -> pd.DataFrame:
    notas = pd.read_excel(BITACORA, sheet_name="Bitácora").reset_index(drop=True)
    etiquetas = pd.read_csv(ETIQUETAS).reset_index(drop=True)
    assert len(notas) == len(etiquetas), "bitácora y etiquetas de laboratorio desalinearon"
    base = notas.join(etiquetas[["_tono_real", "_temas_reales"]])
    return base.sample(n=min(n, len(base)), random_state=semilla).reset_index(drop=True)


def evaluar(n: int = 30, semilla: int = 42, usar_cache: bool = True) -> pd.DataFrame:
    muestra = _muestra(n, semilla)
    filas = []
    for _, r in muestra.iterrows():
        resp = procesar_nota(r["nota"], usar_cache=usar_cache)
        temas_reales = set(r["_temas_reales"].split("|")) if r["_temas_reales"] else set()
        temas_modelo = set(resp.get("temas", []))
        filas.append({
            "employee_id": r["employee_id"],
            "tono_real": TONO_A_SENTIMIENTO[r["_tono_real"]],
            "sentimiento_modelo": resp.get("sentimiento"),
            "acierto_tono": TONO_A_SENTIMIENTO[r["_tono_real"]] == resp.get("sentimiento"),
            "temas_reales": "|".join(sorted(temas_reales)),
            "temas_modelo": "|".join(sorted(temas_modelo)),
            "overlap_temas": len(temas_reales & temas_modelo) > 0 if temas_reales else None,
            "no_procesado": resp.get("sentimiento") == "no_procesado",
        })
    return pd.DataFrame(filas)


def escribir_reporte(df: pd.DataFrame) -> None:
    n = len(df)
    procesadas = df[~df["no_procesado"]]
    acierto_tono = procesadas["acierto_tono"].mean() if len(procesadas) else float("nan")
    overlap = procesadas["overlap_temas"].dropna()
    overlap_pct = overlap.mean() if len(overlap) else float("nan")

    lineas = [
        "# Evaluación de la capa LLM sobre la bitácora",
        "",
        f"Muestra de **{n} notas**, comparadas contra el tono y los temas con que "
        "`generate_data.py` compuso cada nota — la verdad de laboratorio, no una "
        "etiqueta humana. Valida que la tubería (scrubber → prompt → esquema → "
        "verificación de citas) funciona de punta a punta, no que el modelo "
        "'entienda' bitácoras reales de Buk.",
        "",
        f"- Notas procesadas: {len(procesadas)}/{n} "
        f"({n - len(procesadas)} devolvieron `no_procesado`)",
        f"- Acierto de sentimiento (positivo/neutro/negativo): **{acierto_tono:.1%}**",
        f"- Al menos un tema en común con la composición real: **{overlap_pct:.1%}**",
        "",
        "## Detalle",
        "",
        "| employee_id | tono real | sentimiento modelo | acierto | temas reales | temas modelo |",
        "|---|---|---|---|---|---|",
    ]
    for _, r in df.iterrows():
        marca = "✓" if r["acierto_tono"] else ("—" if r["no_procesado"] else "✗")
        lineas.append(
            f"| {r['employee_id']} | {r['tono_real']} | {r['sentimiento_modelo']} | "
            f"{marca} | {r['temas_reales']} | {r['temas_modelo']} |"
        )
    REPORTE.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--semilla", type=int, default=42)
    ap.add_argument("--sin-cache", action="store_true")
    args = ap.parse_args()

    df = evaluar(n=args.n, semilla=args.semilla, usar_cache=not args.sin_cache)
    escribir_reporte(df)
    print(f"{len(df)} notas evaluadas · reporte en {REPORTE.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
