"""
Ingesta: leer las 7 fuentes, hacerlas cumplir su contrato, dejar registro.

Tres decisiones de diseño que vale la pena poder defender:

1. **Cuarentena, no descarte silencioso.** Toda fila que rompe el contrato se
   escribe a `data/out/cuarentena/` con el motivo. Nada desaparece sin dejar
   rastro; alguien puede ir a mirarlas y corregir la planilla de origen.

2. **Campo obligatorio inválido -> se rechaza la fila. Campo opcional inválido
   -> se anula la celda y se deja constancia.** Un CSAT de 0 (imposible en una
   escala 1-5) no invalida la productividad de esa misma fila; una
   productividad de 999% sí invalida la fila entera, porque es la métrica que
   la fila existe para reportar.

3. **Si se rompe demasiado, el pipeline se detiene.** Sobre UMBRAL_RECHAZO de
   filas rechazadas la corrida falla ruidosamente. Un cambio de formato en la
   planilla de origen no puede degradar las alertas en silencio.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import re
import sys
from collections import Counter

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from contratos import CONTRATOS, NULOS_TEXTUALES  # noqa: E402

RAIZ = pathlib.Path(__file__).parent.parent
CRUDO = RAIZ / "data" / "raw"
SALIDA = RAIZ / "data" / "out"
CUARENTENA = SALIDA / "cuarentena"

# Sobre este % de filas rechazadas, la fuente se considera rota y la corrida falla.
UMBRAL_RECHAZO = 0.05

MESES_ES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
            "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12}


# --------------------------------------------------------------------------
# Normalizadores: cada uno recibe lo que sea que había en la celda y devuelve
# el valor tipado, o None si no es interpretable.
# --------------------------------------------------------------------------

def _crudo(v) -> str | None:
    """Texto desnudo: sin espacios sobrantes, con los nulos escritos a mano
    reconocidos como ausencia de dato."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return None if s in NULOS_TEXTUALES else s


def norm_texto(v):
    return _crudo(v)


def norm_numero(v):
    s = _crudo(v)
    if s is None:
        return None
    # Locale es-CL: la planilla trae "94,4" donde BigQuery espera 94.4
    s = s.replace("%", "").replace(" ", "")
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")  # separador de miles
    try:
        return float(s)
    except ValueError:
        return None


def norm_entero(v):
    n = norm_numero(v)
    return None if n is None else int(round(n))


def norm_booleano(v):
    s = _crudo(v)
    if s is None:
        return None
    return s.lower() in {"true", "1", "si", "sí", "verdadero", "yes"}


def norm_fecha(v):
    if isinstance(v, (dt.datetime, pd.Timestamp)):
        return v.date()
    if isinstance(v, dt.date):
        return v
    s = _crudo(v)
    if s is None:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def norm_periodo(v):
    """Un mes calendario como 'YYYY-MM'.

    La planilla de métricas convive con tres formatos porque la mantienen a
    mano: '2026-08', 'ago-2026' y '08/2026'. Los tres significan lo mismo y los
    tres tienen que llegar iguales al warehouse.
    """
    if isinstance(v, (dt.datetime, pd.Timestamp, dt.date)):
        return f"{v.year:04d}-{v.month:02d}"
    s = _crudo(v)
    if s is None:
        return None
    if m := re.fullmatch(r"(\d{4})-(\d{1,2})", s):
        a, me = int(m.group(1)), int(m.group(2))
    elif m := re.fullmatch(r"([a-zA-Záé]{3})\.?-(\d{4})", s):
        me, a = MESES_ES.get(m.group(1)[:3].lower()), int(m.group(2))
    elif m := re.fullmatch(r"(\d{1,2})/(\d{4})", s):
        me, a = int(m.group(1)), int(m.group(2))
    else:
        return None
    if not me or not 1 <= me <= 12:
        return None
    return f"{a:04d}-{me:02d}"


NORMALIZADORES = {
    "texto": norm_texto, "numero": norm_numero, "entero": norm_entero,
    "fecha": norm_fecha, "periodo": norm_periodo, "booleano": norm_booleano,
}


# --------------------------------------------------------------------------
# Reporte de calidad
# --------------------------------------------------------------------------

class Reporte:
    """Acumula todo lo que salió mal, agrupado por fuente y tipo de incidencia."""

    def __init__(self):
        self.fuentes: dict[str, dict] = {}
        self.incidencias: list[dict] = []

    def anotar(self, fuente, tipo, columna, detalle, n=1):
        self.incidencias.append({"fuente": fuente, "tipo": tipo, "columna": columna,
                                 "detalle": detalle, "filas": n})

    def resumen_fuente(self, fuente, **kv):
        self.fuentes.setdefault(fuente, {}).update(kv)

    def tabla(self) -> pd.DataFrame:
        if not self.incidencias:
            return pd.DataFrame(columns=["fuente", "tipo", "columna", "detalle", "filas"])
        df = pd.DataFrame(self.incidencias)
        return (df.groupby(["fuente", "tipo", "columna", "detalle"], as_index=False)["filas"]
                  .sum().sort_values("filas", ascending=False))


# --------------------------------------------------------------------------
# Lectura y validación
# --------------------------------------------------------------------------

def leer(nombre: str, contrato: dict) -> pd.DataFrame:
    ruta = CRUDO / contrato["archivo"]
    if not ruta.exists():
        raise FileNotFoundError(f"Fuente '{nombre}' no encontrada en {ruta}")
    if contrato["formato"] == "csv":
        df = pd.read_csv(ruta, dtype=object, keep_default_na=False)
    else:
        df = pd.read_excel(ruta, sheet_name=contrato.get("hoja", 0), dtype=object)
    # Encabezados escritos a mano: espacios sobrantes y nombres libres.
    df.columns = [str(c).strip() for c in df.columns]
    if ren := contrato.get("renombrar"):
        df = df.rename(columns={k.strip(): v for k, v in ren.items()})
    return df


# --------------------------------------------------------------------------
# Reparaciones: lo que se arregla en silencio, contado en voz alta
# --------------------------------------------------------------------------

def reparaciones(nombre: str, df: pd.DataFrame, cols: dict, rep: Reporte) -> None:
    """Cuenta las correcciones aplicadas antes de tipar.

    Sin esto, el reporte solo muestra lo que se rechazó y la limpieza queda
    invisible: 564 identificadores con espacios sobrantes se arreglan sin que
    nadie se entere de que estaban rotos. Y si mañana el origen empieza a
    mandar el 100% de las fechas en otro formato, esa cifra es la única señal
    temprana de que algo cambió aguas arriba.
    """
    for col, spec in cols.items():
        if col not in df.columns:
            continue
        s = df[col].map(lambda v: None if v is None or (isinstance(v, float) and pd.isna(v))
                        else str(v))
        vivo = s.notna()

        n = int((vivo & (s != s.str.strip())).sum())
        if n:
            rep.anotar(nombre, "reparado_espacios", col,
                       "espacios sobrantes al inicio/fin", n)

        limpio_s = s.str.strip()
        n = int((vivo & limpio_s.isin(NULOS_TEXTUALES - {""})).sum())
        if n:
            ej = sorted(set(limpio_s[limpio_s.isin(NULOS_TEXTUALES - {""})].head(50)))[:4]
            rep.anotar(nombre, "reparado_nulo_textual", col,
                       f"nulo escrito a mano {ej} leído como ausencia de dato", n)

        if spec["tipo"] in ("numero", "entero"):
            n = int((vivo & limpio_s.str.fullmatch(r"-?\d+,\d+", na=False)).sum())
            if n:
                rep.anotar(nombre, "reparado_decimal_coma", col,
                           "coma decimal es-CL convertida a punto", n)

        if spec["tipo"] == "periodo":
            # Cuántos períodos no venían ya en el formato canónico YYYY-MM
            no_iso = vivo & ~limpio_s.str.fullmatch(r"\d{4}-\d{2}", na=False)
            if int(no_iso.sum()):
                formas = Counter(
                    "texto-mes" if re.fullmatch(r"[a-zA-Záé]{3}\.?-\d{4}", v) else
                    "MM/YYYY" if re.fullmatch(r"\d{1,2}/\d{4}", v) else "otro"
                    for v in limpio_s[no_iso])
                rep.anotar(nombre, "reparado_formato_fecha", col,
                           f"normalizado a YYYY-MM desde {dict(formas)}", int(no_iso.sum()))


def validar(nombre: str, contrato: dict, df: pd.DataFrame, rep: Reporte) -> pd.DataFrame:
    """Aplica el contrato. Devuelve solo las filas que lo cumplen."""
    n_entrada = len(df)
    cols = contrato["columnas"]

    faltantes = [c for c in cols if c not in df.columns]
    if faltantes:
        # Una columna que no llegó no es una fila mala: es un cambio de esquema
        # en el origen. Se detiene aquí, antes de calcular nada sobre ella.
        raise ValueError(
            f"Fuente '{nombre}' rompió su contrato: faltan columnas {faltantes}. "
            f"Llegaron: {list(df.columns)}")

    df = df[list(cols)].copy()

    # 1. Contar lo que hay que reparar, antes de repararlo
    reparaciones(nombre, df, cols, rep)

    # 2. Normalización de tipos
    for col, spec in cols.items():
        df[col] = df[col].map(NORMALIZADORES[spec["tipo"]])

    motivos = pd.Series([""] * len(df), index=df.index)

    def marcar(mascara, motivo):
        nuevo = mascara & (motivos == "")
        motivos.loc[nuevo] = motivo
        return int(nuevo.sum())

    # 3. Reglas por columna
    for col, spec in cols.items():
        nulos = df[col].isna()
        if spec.get("requerido"):
            if n := marcar(nulos, f"{col}: obligatorio ausente o ilegible"):
                rep.anotar(nombre, "obligatorio_ausente", col, "nulo o formato ilegible", n)
        elif nulos.any():
            rep.anotar(nombre, "nulo_opcional", col, "sin dato (se conserva la fila)",
                       int(nulos.sum()))

        presente = ~df[col].isna()

        if pat := spec.get("patron"):
            malo = presente & ~df[col].astype(str).str.fullmatch(pat, na=False)
            if n := marcar(malo, f"{col}: no calza patrón {pat}"):
                rep.anotar(nombre, "patron_invalido", col, f"no calza {pat}", n)

        if vals := spec.get("valores"):
            malo = presente & ~df[col].isin(vals)
            if malo.any():
                ejemplos = sorted({str(v) for v in df.loc[malo, col].head(5)})
                if n := marcar(malo, f"{col}: valor fuera del dominio"):
                    rep.anotar(nombre, "valor_no_permitido", col, f"ej. {ejemplos}", n)

        if spec["tipo"] in ("numero", "entero") and ("min" in spec or "max" in spec):
            lo, hi = spec.get("min", -float("inf")), spec.get("max", float("inf"))
            serie = pd.to_numeric(df[col], errors="coerce")
            malo = presente & ((serie < lo) | (serie > hi))
            if malo.any():
                ejemplos = sorted({float(v) for v in serie[malo].head(200)})[:4]
                if spec.get("requerido"):
                    # La fila existe para reportar este número. Si es imposible,
                    # no hay fila que salvar.
                    n = marcar(malo, f"{col}: fuera de rango [{lo}, {hi}]")
                    rep.anotar(nombre, "fuera_de_rango_rechaza", col,
                               f"esperado [{lo}, {hi}], ej. {ejemplos}", n)
                else:
                    # Métrica accesoria imposible: se anula la celda y el resto
                    # de la fila sigue siendo utilizable.
                    df.loc[malo, col] = None
                    rep.anotar(nombre, "fuera_de_rango_anula", col,
                               f"esperado [{lo}, {hi}], ej. {ejemplos}", int(malo.sum()))

        if lmin := spec.get("largo_min"):
            corto = presente & (df[col].astype(str).str.len() < lmin)
            if n := marcar(corto, f"{col}: texto más corto que {lmin} caracteres"):
                rep.anotar(nombre, "texto_insuficiente", col, f"< {lmin} caracteres", n)

    rechazadas = df[motivos != ""].copy()
    rechazadas["_motivo_rechazo"] = motivos[motivos != ""]
    limpio = df[motivos == ""].copy()

    # 4. Duplicados por clave (copiar y pegar en la planilla)
    clave = contrato["clave"]
    dup = limpio.duplicated(subset=clave, keep="first")
    if dup.any():
        rep.anotar(nombre, "duplicado_clave", "+".join(clave),
                   "se conserva la primera ocurrencia", int(dup.sum()))
        limpio = limpio[~dup]

    if len(rechazadas):
        CUARENTENA.mkdir(parents=True, exist_ok=True)
        rechazadas.to_csv(CUARENTENA / f"{nombre}.csv", index=False)

    tasa = len(rechazadas) / n_entrada if n_entrada else 0.0
    rep.resumen_fuente(nombre, archivo=contrato["archivo"], descripcion=contrato["descripcion"],
                       filas_entrada=n_entrada, filas_validas=len(limpio),
                       rechazadas=len(rechazadas), duplicadas=int(dup.sum()),
                       tasa_rechazo=tasa)

    if tasa > UMBRAL_RECHAZO:
        top = Counter(rechazadas["_motivo_rechazo"]).most_common(3)
        raise ValueError(
            f"Fuente '{nombre}': {tasa:.1%} de filas rechazadas, sobre el umbral "
            f"de {UMBRAL_RECHAZO:.0%}. Motivos principales: {top}. "
            f"Revisar {CUARENTENA / f'{nombre}.csv'} antes de volver a correr.")

    return limpio


# --------------------------------------------------------------------------
# Integridad referencial: lo que ningún contrato de columna puede ver
# --------------------------------------------------------------------------

def integridad(tablas: dict[str, pd.DataFrame], rep: Reporte) -> dict[str, pd.DataFrame]:
    dir_ = tablas["directorio"]
    conocidos = set(dir_["employee_id"])

    for nombre, df in tablas.items():
        if nombre in ("directorio", "dim_cargos") or "employee_id" not in df.columns:
            continue
        huerfanas = ~df["employee_id"].isin(conocidos)
        if huerfanas.any():
            rep.anotar(nombre, "huerfano", "employee_id",
                       "id sin correspondencia en el directorio", int(huerfanas.sum()))
            tablas[nombre] = df[~huerfanas]

    # El chequeo de gobernanza: todo cargo del directorio tiene que mapear a la
    # tabla dimensional. Es el test que se rompe cuando alguien crea un cargo
    # nuevo y no lo declara. Con ~325 cambios internos al año en Latam, esto
    # no es una hipótesis: es mantenimiento de rutina.
    dim = tablas["dim_cargos"]
    mapeados = set(zip(dim["cargo"], dim["pais_contrato"]))
    sin_mapeo = [c for c in set(zip(dir_["cargo"], dir_["pais_contrato"])) if c not in mapeados]
    if sin_mapeo:
        rep.anotar("directorio", "cargo_sin_mapeo", "cargo+pais_contrato",
                   f"ej. {sorted(sin_mapeo)[:5]}", len(sin_mapeo))
        raise ValueError(
            f"{len(sin_mapeo)} combinación(es) cargo x país del directorio no existen en "
            f"dim_cargos: {sorted(sin_mapeo)[:5]}. Las reglas de negocio referencian "
            f"job_family x job_level desde esa tabla; un cargo sin mapeo produciría "
            f"alertas sin banda salarial de comparación. Declarar el cargo y re-correr.")

    rep.resumen_fuente("directorio", cargos_sin_mapeo=len(sin_mapeo))
    return tablas


# --------------------------------------------------------------------------

def ingestar(verboso: bool = True) -> tuple[dict[str, pd.DataFrame], Reporte]:
    rep = Reporte()
    tablas = {}
    for nombre, contrato in CONTRATOS.items():
        crudo = leer(nombre, contrato)
        tablas[nombre] = validar(nombre, contrato, crudo, rep)
        if verboso:
            r = rep.fuentes[nombre]
            marca = "  " if r["rechazadas"] == 0 else " !"
            print(f"{marca} {nombre:24} {r['filas_entrada']:>7,} -> {r['filas_validas']:>7,} "
                  f"filas  ({r['rechazadas']} rechazadas, {r['duplicadas']} duplicadas)")
    tablas = integridad(tablas, rep)
    return tablas, rep


def escribir_reporte(rep: Reporte) -> pathlib.Path:
    SALIDA.mkdir(parents=True, exist_ok=True)
    ruta = SALIDA / "reporte_calidad.md"
    inc = rep.tabla()

    tot_in = sum(f["filas_entrada"] for f in rep.fuentes.values())
    tot_ok = sum(f["filas_validas"] for f in rep.fuentes.values())

    L = ["# Reporte de calidad de datos",
         "",
         f"Generado: {dt.datetime.now():%Y-%m-%d %H:%M} · "
         f"{len(rep.fuentes)} fuentes · {tot_in:,} filas leídas · {tot_ok:,} válidas "
         f"({tot_ok / tot_in:.1%})",
         "",
         "Artefacto autogenerado por `src/ingest.py`. Toda fila rechazada queda en "
         "`data/out/cuarentena/` con su motivo: nada se descarta en silencio.",
         "",
         "## Por fuente",
         "",
         "| Fuente | Origen | Leídas | Válidas | Rechazadas | Duplicadas | Tasa rechazo |",
         "|---|---|---:|---:|---:|---:|---:|"]
    for n, f in rep.fuentes.items():
        L.append(f"| {n} | `{f['archivo']}` | {f['filas_entrada']:,} | {f['filas_validas']:,} | "
                 f"{f['rechazadas']} | {f['duplicadas']} | {f['tasa_rechazo']:.2%} |")

    L += ["", "## Incidencias detectadas", ""]
    if inc.empty:
        L.append("Ninguna.")
    else:
        L += ["| Fuente | Tipo | Columna | Detalle | Filas |", "|---|---|---|---|---:|"]
        for r in inc.itertuples():
            L.append(f"| {r.fuente} | `{r.tipo}` | `{r.columna}` | {r.detalle} | {r.filas:,} |")

    L += ["", "## Cómo leer los tipos de incidencia", "",
          "| Tipo | Qué significa | Qué se hace con la fila |",
          "|---|---|---|",
          "| `obligatorio_ausente` | Un campo sin el cual la fila no significa nada | Se rechaza |",
          "| `patron_invalido` | El identificador no tiene la forma `BUK#####` | Se rechaza |",
          "| `valor_no_permitido` | Categoría fuera del dominio declarado | Se rechaza |",
          "| `fuera_de_rango_rechaza` | Métrica principal imposible (productividad 999%) | Se rechaza |",
          "| `fuera_de_rango_anula` | Métrica accesoria imposible (CSAT 0 en escala 1-5) | Se anula la celda, se conserva la fila |",
          "| `nulo_opcional` | Dato accesorio ausente | Se conserva |",
          "| `duplicado_clave` | Misma clave repetida (copiar y pegar en la planilla) | Se conserva la primera |",
          "| `huerfano` | `employee_id` que no existe en el directorio | Se rechaza |",
          "| `cargo_sin_mapeo` | Cargo del directorio ausente de `dim_cargos` | **Detiene la corrida** |",
          "| `reparado_*` | Se corrigió en la ingesta y la fila sigue su curso | Se conserva, corregida |",
          "",
          f"Sobre {UMBRAL_RECHAZO:.0%} de filas rechazadas en una fuente, el pipeline se "
          "detiene en vez de producir alertas sobre datos degradados."]

    ruta.write_text("\n".join(L), encoding="utf-8")
    return ruta


if __name__ == "__main__":
    tablas, rep = ingestar()
    ruta = escribir_reporte(rep)
    print(f"\nReporte: {ruta.relative_to(RAIZ)}")
