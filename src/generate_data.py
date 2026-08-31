"""
Generador del universo sintético de bukers.

Simula 2.000 colaboradores activos + el histórico de salidas de 24 meses, y
escribe siete fuentes en los formatos nativos que declara el caso (tablas
BigQuery como CSV, planillas de Google Sheets como XLSX).

MODELO CAUSAL
-------------
Cada persona recibe un perfil latente que gobierna una trayectoria mensual de
"engagement". De esa trayectoria se derivan, con ruido, TODAS las observables:
desempeño, productividad, CSAT, días sin vacaciones, cursos, el tono de su
bitácora y su probabilidad de salir.

Que exista esta estructura es lo que permite que las reglas encuentren señal.
Y es exactamente por eso que el backtest valida el MÉTODO de calibración, no la
eficacia del sistema en el mundo real: aquí la señal está puesta a mano.
"""
from __future__ import annotations

import datetime as dt
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

sys.path.insert(0, str(Path(__file__).parent))
import refdata as rd
import textos as tx

SEMILLA = 20260902
AS_OF = dt.date(2026, 8, 31)
N_ACTIVOS = 2_000
N_SALIDAS = 650          # 24 meses de histórico (~12% de rotación anual)
MESES_OPERATIVOS = 12    # ventana de métricas mensuales

# Inclinación por mérito de la compensación. Traduce la diferencia de nivel basal
# de una persona respecto al promedio en posición dentro de su banda: con una
# pendiente de 0.19 sobre un rango de `eng_base` de ~0.37, el compa-ratio de un
# Sobresaliente queda ~0.07 sobre el de un Bajo lo esperado.
MERITO_PENDIENTE = 0.19
ENG_BASE_MEDIA = 0.745
RAIZ = Path(__file__).resolve().parent.parent
CRUDO = RAIZ / "data" / "raw"

rng = np.random.default_rng(SEMILLA)
random.seed(SEMILLA)
Faker.seed(SEMILLA)
FAKERS = {
    "latam": Faker("es_CL"), "mx": Faker("es_MX"), "co": Faker("es_CO"),
    "br": Faker("pt_BR"), "eu": Faker("es_ES"), "en": Faker("en_US"),
}
_LOCALE_POR_NACIONALIDAD = {
    "Brasileña": "br", "Portuguesa": "br", "Mexicana": "mx", "Colombiana": "co",
    "Española": "eu", "Italiana": "eu", "Francesa": "eu", "Alemana": "eu",
    "Británica": "en", "Estadounidense": "en", "Canadiense": "en",
    "Australiana": "en", "Neozelandesa": "en",
}


def _elige(opciones: dict | list, pesos=None):
    if isinstance(opciones, dict):
        claves, pesos = list(opciones.keys()), list(opciones.values())
    else:
        claves = opciones
    p = None if pesos is None else np.array(pesos, dtype=float) / np.sum(pesos)
    return rng.choice(claves, p=p)


def _meses(desde: dt.date, n: int) -> list[str]:
    """Lista de n períodos YYYY-MM terminando en `desde`."""
    out, y, m = [], desde.year, desde.month
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


# ---------------------------------------------------------------------------
# 1. Población y atributos estructurales
# ---------------------------------------------------------------------------
def construir_poblacion() -> pd.DataFrame:
    cargos = pd.DataFrame(rd.dim_cargos())
    filas = []
    total = N_ACTIVOS + N_SALIDAS

    for i in range(total):
        pais = _elige({k: v[3] for k, v in rd.PAISES_CONTRATO.items()})
        familia = _elige(rd.PESO_FAMILIA)
        nivel = _elige({k: v[2] for k, v in rd.NIVELES.items()})

        opciones = cargos[(cargos.job_family == familia) &
                          (cargos.job_level == nivel) &
                          (cargos.pais_contrato == pais)]
        cargo = opciones.sample(1, random_state=int(rng.integers(0, 1 << 31))).iloc[0]

        nacionalidad = _elige([n for n, _ in rd.NACIONALIDADES],
                              [w for _, w in rd.NACIONALIDADES])
        fk = FAKERS[_LOCALE_POR_NACIONALIDAD.get(nacionalidad, "latam")]

        # Género: Buk declara 54% mujeres
        genero = _elige(["F", "M", "No binario / No informa"], [0.54, 0.445, 0.015])
        nombre = fk.name_female() if genero == "F" else fk.name_male()

        # Edad promedio declarada: 31 años
        edad = float(np.clip(rng.normal(31, 6.2), 21, 62))
        nacimiento = AS_OF - dt.timedelta(days=int(edad * 365.25))

        # Antigüedad coherente con la expansión por país y el crecimiento reciente
        apertura = dt.date(rd.PAISES_CONTRATO[pais][2], 1, 1)
        max_ant = (AS_OF - apertura).days
        ant_dias = int(min(max_ant, rng.exponential(700) + rng.integers(20, 90)))
        ingreso = AS_OF - dt.timedelta(days=ant_dias)

        # WFA: ~9% reside en un país distinto al de su contrato
        if rng.random() < 0.09:
            residencia = str(_elige([p for p in rd.PAISES_CONTRATO if p != pais] + ["ES", "AR", "PT"]))
        else:
            residencia = pais

        filas.append({
            "employee_id": f"BUK{10000 + i}",
            "nombre": nombre,
            "email": f"{nombre.split()[0].lower()}.{nombre.split()[-1].lower()}@buk.example",
            "genero": genero,
            "fecha_nacimiento": nacimiento.isoformat(),
            "nacionalidad": nacionalidad,
            "pais_contrato": pais,
            "pais_residencia": residencia,
            "modalidad": str(_elige(["Híbrido", "Remoto", "Presencial"], [0.52, 0.38, 0.10])),
            "area": cargo.area,
            "cargo": cargo.cargo,
            "job_family": familia,
            "job_level": nivel,
            "es_liderazgo": bool(cargo.es_liderazgo),
            "fecha_ingreso": ingreso.isoformat(),
            "tipo_contrato": str(_elige(["Indefinido", "Plazo fijo"], [0.93, 0.07])),
            "situacion_discapacidad": bool(rng.random() < 0.021),
            # El estado se decide en marcar_desvinculados(), una vez que existe
            # el perfil latente. Aquí todos nacen activos.
            "estado": "Activo",
            "moneda": cargo.moneda,
            "banda_min": float(cargo.banda_min),
            "banda_med": float(cargo.banda_med),
            "banda_max": float(cargo.banda_max),
        })

    df = pd.DataFrame(filas)

    # Autodeclaración voluntaria de diversidad sexual: alta nulidad a propósito.
    # Es dato sensible de declaración opcional; se usa SOLO para auditar equidad.
    df["diversidad_sexual_declarada"] = [
        str(_elige(["Sí", "Prefiero no responder", ""], [0.09, 0.16, 0.75])) for _ in range(len(df))
    ]

    df["manager_id"] = _asignar_jerarquia(df)
    return df


def _asignar_jerarquia(df: pd.DataFrame) -> list[str]:
    """Cada nivel reporta al nivel de liderazgo inmediatamente superior de su área.

    Se resuelve por área y con fallback global, de modo que nadie —salvo los
    gerentes— quede sin líder asignado. Un colaborador sin líder es un hueco de
    datos que después rompe cualquier análisis de equipo.
    """
    activos = df[df.estado == "Activo"]
    por_nivel_area, por_nivel = {}, {}
    for nivel in ("M1", "M2", "M3"):
        grupo = activos[activos.job_level == nivel]
        por_nivel[nivel] = grupo.employee_id.tolist()
        for area, g in grupo.groupby("area"):
            por_nivel_area[(nivel, area)] = g.employee_id.tolist()

    siguiente = {"M3": None, "M2": "M3", "M1": "M2"}
    out = []
    for r in df.itertuples():
        nivel_jefe = siguiente.get(r.job_level, "M1")
        if nivel_jefe is None:
            out.append("")
            continue
        candidatos = por_nivel_area.get((nivel_jefe, r.area)) or por_nivel.get(nivel_jefe) or []
        candidatos = [c for c in candidatos if c != r.employee_id]
        out.append(random.choice(candidatos) if candidatos else "")
    return out


# ---------------------------------------------------------------------------
# 2. Trayectoria latente de engagement
# ---------------------------------------------------------------------------
def asignar_perfiles(df: pd.DataFrame) -> pd.DataFrame:
    """Perfil latente + parámetros de la trayectoria de engagement."""
    perfiles, bases, pendientes, declives = [], [], [], []
    interceptos, interceptos_csat = [], []
    for _ in range(len(df)):
        p = str(_elige(rd.PERFILES))
        if p == "estable":
            base, pend = rng.normal(0.79, 0.075), rng.normal(0.000, 0.004)
        elif p == "deterioro":
            base, pend = rng.normal(0.74, 0.070), -abs(rng.normal(0.030, 0.010))
        elif p == "estrella_subpagada":
            base, pend = rng.normal(0.76, 0.070), -abs(rng.normal(0.013, 0.007))
        elif p == "bajo_desempeno":
            base, pend = rng.normal(0.44, 0.090), rng.normal(-0.004, 0.006)
        else:  # nuevo_dificil
            base, pend = rng.normal(0.52, 0.090), -abs(rng.normal(0.012, 0.008))
        perfiles.append(p); bases.append(base); pendientes.append(pend)
        # Cuántos meses dura el descenso antes de tocar fondo. Que varíe entre
        # personas es lo que hace medible la anticipación: si todos cayeran en
        # el mismo plazo, "detectado con 60 días de antelación" sería una
        # constante del generador y no una propiedad de las reglas.
        declives.append(int(rng.integers(6, 16)))
        # Nivel propio y persistente de cada persona. Sin él, toda la diferencia
        # entre personas venía del engagement y el resto era ruido mensual: el
        # mismo individuo oscilaba más de un mes a otro que lo que se distinguía
        # de sus pares. En los datos reales es al revés — quien entrega 105% de
        # forma consistente no salta a 90% y vuelve. Y como las reglas leen
        # tendencias (deltas dentro de la misma persona), ese ruido las volvía
        # inservibles: marcaba al 25% de la gente sana.
        interceptos.append(float(rng.normal(0, 6.0)))
        interceptos_csat.append(float(rng.normal(0, 0.22)))

    df = df.copy()
    df["perfil_latente"] = perfiles
    df["eng_base"] = bases
    df["eng_pendiente"] = pendientes
    df["declive_meses"] = declives
    df["prod_intercepto"] = interceptos
    df["csat_intercepto"] = interceptos_csat
    # Los perfiles de onboarding difícil solo aplican a gente con poca antigüedad
    reciente = (pd.to_datetime(AS_OF) - pd.to_datetime(df.fecha_ingreso)).dt.days < 400
    df.loc[(df.perfil_latente == "nuevo_dificil") & ~reciente, "perfil_latente"] = "estable"
    return df


def marcar_desvinculados(df: pd.DataFrame) -> pd.DataFrame:
    """Decide quién sale, en función del perfil latente.

    Esto tiene que ocurrir DESPUÉS de asignar perfiles, y es la corrección de un
    error real que tuvo esta simulación: al marcar el estado por posición en el
    bucle de construcción, salir de Buk quedaba estadísticamente independiente
    del deterioro. El 70% de las salidas venía de gente sin ninguna señal, y
    ninguna regla —por buena que fuera— podía superar el azar. Un generador que
    no acopla causa y efecto produce un backtest que miente en las dos
    direcciones: no detecta lo que debería y no permite calibrar nada.

    Las propensidades no son deterministas a propósito. Cerca de un tercio de
    las salidas viene del perfil `estable`: gente que se va por razones que
    ningún dato interno anticipa (una oferta inesperada, una mudanza, un cambio
    de vida). Ese tercio es el techo de recall del sistema, y es sano que
    exista: un backtest que detecta el 100% describiría un mundo donde las
    personas son predecibles, no un sistema que funciona.
    """
    propension = {"estable": 1.0, "deterioro": 4.5, "estrella_subpagada": 4.0,
                  "bajo_desempeno": 4.2, "nuevo_dificil": 4.0}
    w = df.perfil_latente.map(propension).to_numpy(dtype=float)
    idx = rng.choice(len(df), size=N_SALIDAS, replace=False, p=w / w.sum())
    df = df.copy()
    df.loc[df.index[idx], "estado"] = "Desvinculado"
    return df


def anclar_trayectorias(df: pd.DataFrame) -> pd.DataFrame:
    """Fija dónde toca fondo la trayectoria de cada persona.

    Segundo error de acoplamiento de esta simulación, hermano del anterior. El
    engagement se calculaba contra el calendario: todo el mundo empezaba alto en
    marzo 2025 y descendía hacia agosto 2026. Pero las salidas se repartían
    uniformemente en 24 meses, así que alguien con perfil `deterioro` que
    renunció en junio 2025 apenas había empezado a caer cuando se fue. Su
    deterioro "ocurría" meses después de que ya no estaba.

    El efecto medible: las reglas marcaban al 25% de quienes se iban y al 28% de
    quienes se quedaban. Lift negativo. No porque las reglas estuvieran mal, sino
    porque en los datos la causa no precedía al efecto.

    Corrección: el descenso se ancla a la fecha de salida y culmina ahí. Para
    quien sigue activo el ancla es el corte del análisis, con dispersión de hasta
    6 meses hacia adelante: parte de la gente en riesgo está a mitad de camino,
    no toda en el fondo. Sin esa dispersión, la lista de alertas del mes saldría
    artificialmente limpia.
    """
    meses = _meses(AS_OF, MESES_VENTANA)
    idx0 = int(meses[0][:4]) * 12 + int(meses[0][5:7]) - 1
    anclas = []
    for f in df.fecha_salida_dt:
        if isinstance(f, dt.date):
            anclas.append(int(np.clip(f.year * 12 + f.month - 1 - idx0, 0, MESES_VENTANA - 1)))
        else:
            anclas.append(MESES_VENTANA - 1 + int(rng.integers(0, 7)))
    df = df.copy()
    df["idx_ancla"] = anclas
    return df


def engagement(fila, idx_mes: int, n_meses: int) -> float:
    """Engagement latente en el mes `idx_mes` (0 = más antiguo de la ventana).

    Se mide contra el ancla de la persona, no contra el calendario: `avance` va
    de 0 (lejos del ancla, todavía en su nivel base) a `declive_meses` (en el
    fondo). Ver anclar_trayectorias().
    """
    faltan = fila.idx_ancla - idx_mes
    avance = fila.declive_meses - min(max(faltan, 0), fila.declive_meses)
    val = fila.eng_base + fila.eng_pendiente * avance
    return float(np.clip(val + rng.normal(0, 0.022), 0.03, 0.99))


def _fecha_fin(fila) -> dt.date:
    """Último día con datos: la salida si se desvinculó, o el corte del análisis."""
    f = getattr(fila, "fecha_salida_dt", None)
    return f if isinstance(f, dt.date) else AS_OF


# ---------------------------------------------------------------------------
# 3. Salidas (se resuelven primero: acotan la ventana de datos de cada persona)
# ---------------------------------------------------------------------------
def generar_salidas(df: pd.DataFrame) -> pd.DataFrame:
    """Desvinculaciones de los últimos 24 meses + entrevista de salida."""
    salidas, fechas = [], {}
    desvinculados = df[df.estado == "Desvinculado"]

    for r in desvinculados.itertuples():
        ingreso = dt.date.fromisoformat(r.fecha_ingreso)
        # La salida ocurre en algún punto de los últimos 24 meses, siempre
        # después del ingreso y con al menos dos meses de permanencia.
        min_salida = max(ingreso + dt.timedelta(days=60), AS_OF - dt.timedelta(days=730))
        if min_salida >= AS_OF:
            min_salida = AS_OF - dt.timedelta(days=90)
        dias = int(rng.integers(0, max(1, (AS_OF - min_salida).days)))
        fecha_salida = min_salida + dt.timedelta(days=dias)

        # El perfil latente gobierna si la salida es voluntaria o no
        if r.perfil_latente in ("deterioro", "estrella_subpagada"):
            voluntaria = rng.random() < 0.90
        elif r.perfil_latente in ("bajo_desempeno", "nuevo_dificil"):
            voluntaria = rng.random() < 0.25
        else:
            voluntaria = rng.random() < 0.75

        if voluntaria:
            if r.perfil_latente == "estrella_subpagada":
                motivo = str(_elige(["Mejor oferta económica", "Falta de oportunidades de desarrollo",
                                     "Cambio de rubro o proyecto personal"], [0.62, 0.28, 0.10]))
            elif r.perfil_latente == "deterioro":
                motivo = str(_elige(["Carga de trabajo y desgaste", "Relación con la jefatura",
                                     "Falta de oportunidades de desarrollo", "Mejor oferta económica"],
                                    [0.32, 0.26, 0.24, 0.18]))
            else:
                motivo = str(_elige(tx.MOTIVOS_SALIDA_VOLUNTARIA))
        else:
            motivo = str(_elige(tx.MOTIVOS_SALIDA_INVOLUNTARIA, [0.42, 0.28, 0.12, 0.18]))

        # "Lamentada": salida voluntaria de alguien que cumplía o superaba lo
        # esperado. Es la métrica que de verdad le duele al negocio y el objetivo
        # real del sistema — no toda salida es un problema a prevenir.
        p_lamentada = {"estrella_subpagada": 0.95, "deterioro": 0.82,
                       "estable": 0.78}.get(r.perfil_latente, 0.10)
        lamentada = bool(voluntaria and rng.random() < p_lamentada)

        fechas[r.employee_id] = fecha_salida
        salidas.append({
            "employee_id": r.employee_id,
            "fecha_salida": fecha_salida.isoformat(),
            "tipo_salida": "Voluntaria" if voluntaria else "No voluntaria",
            "motivo_declarado": motivo,
            "salida_lamentada": lamentada,
            "meses_en_buk": round((fecha_salida - ingreso).days / 30.44, 1),
            "texto_entrevista_salida": tx.SALIDA_TEXTO[motivo],
        })

    df["fecha_salida_dt"] = df.employee_id.map(fechas)
    return pd.DataFrame(salidas).sort_values("fecha_salida", ascending=False)


# ---------------------------------------------------------------------------
# 4. Compensaciones
# ---------------------------------------------------------------------------
def generar_compensaciones(df: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for r in df.itertuples():
        ant_anios = (_fecha_fin(r) - dt.date.fromisoformat(r.fecha_ingreso)).days / 365.25

        if r.perfil_latente == "estrella_subpagada":
            # El caso de equidad interna: buen desempeño, posición baja en banda.
            # Es la excepción deliberada al mérito: la fuga entre la política
            # declarada y la práctica, que es justo lo que la regla debe cazar.
            compa = rng.normal(0.845, 0.045)
            meses_ajuste = int(np.clip(rng.normal(20, 5), 13, 34))
        else:
            # Buk declara "Mérito y Desempeño" como uno de sus cuatro lineamientos
            # de compensación, así que quien rinde mejor tiene que quedar más
            # arriba en su banda. El mérito se ancla en `eng_base` —el nivel
            # basal de la persona— y no en su engagement del mes: el sueldo
            # refleja lo que se decidió en el último ajuste, no el deterioro
            # posterior. Sin este término, un buen desempeño y uno bajo quedan
            # indistinguibles en banda, que es lo contrario de lo que la
            # política produce.
            merito = MERITO_PENDIENTE * (r.eng_base - ENG_BASE_MEDIA)
            compa = rng.normal(0.97 + min(ant_anios, 5) * 0.017 + merito, 0.085)
            meses_ajuste = int(np.clip(rng.exponential(9) + 1, 1, 36))
        compa = float(np.clip(compa, 0.70, 1.38))

        # El ajuste no puede ser anterior al ingreso
        meses_ajuste = min(meses_ajuste, max(1, int(ant_anios * 12)))
        fecha_ajuste = _fecha_fin(r) - dt.timedelta(days=int(meses_ajuste * 30.44))

        paso = {"CLP": 10_000, "COP": 50_000, "PEN": 100, "MXN": 500, "BRL": 100}[r.moneda]
        sueldo = round(r.banda_med * compa / paso) * paso

        filas.append({
            "employee_id": r.employee_id,
            "moneda": r.moneda,
            "sueldo_base": float(sueldo),
            "banda_min": r.banda_min, "banda_med": r.banda_med, "banda_max": r.banda_max,
            "compa_ratio": round(sueldo / r.banda_med, 4),
            "posicion_en_banda": round((sueldo - r.banda_min) / (r.banda_max - r.banda_min), 4),
            "fecha_ultimo_ajuste": fecha_ajuste.isoformat(),
            "meses_desde_ultimo_ajuste": meses_ajuste,
            "tiene_incentivo_variable": r.job_family in ("Ventas",),
        })
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# 5. Evaluaciones (escala 1 a 4, la que usa Buk)
# ---------------------------------------------------------------------------
def _nota(eng: float, sigma: float = 0.20) -> float:
    """Traduce engagement latente a la escala 1-4 de Buk.

    Referencia del Culture Code: <3 bajo desempeño, 3-3.4 cumple lo esperado,
    3.5-4 sobresaliente.
    """
    return float(np.clip(1.72 + 2.18 * eng + rng.normal(0, sigma), 1.0, 4.0))


def generar_eval_90d(df: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for r in df.itertuples():
        ingreso = dt.date.fromisoformat(r.fecha_ingreso)
        fecha_eval = ingreso + dt.timedelta(days=95)
        if fecha_eval > _fecha_fin(r):
            continue  # aún no le corresponde, o salió antes
        eng_inicial = float(np.clip(r.eng_base + rng.normal(0, 0.06), 0.03, 0.99))
        desempeno = _nota(eng_inicial, 0.24)
        cultura = _nota(eng_inicial * 0.9 + 0.08, 0.26)
        if min(desempeno, cultura) < 2.4:
            reco = "No superó el período de prueba"
        elif min(desempeno, cultura) < 3.0:
            reco = "Continuar con seguimiento"
        else:
            reco = "Continuar"
        filas.append({
            "employee_id": r.employee_id,
            "fecha_evaluacion": fecha_eval.isoformat(),
            "score_desempeno": round(desempeno, 2),
            "score_adaptacion_cultural": round(cultura, 2),
            "recomendacion": reco,
            "evaluador_id": r.manager_id,
        })
    return pd.DataFrame(filas)


def generar_eval_desempeno(df: pd.DataFrame) -> pd.DataFrame:
    """Ciclo anual (diciembre) + mid year feedback (julio), como declara Buk."""
    hitos = [
        ("2024-Anual", dt.date(2024, 12, 10), "Anual"),
        ("2025-MidYear", dt.date(2025, 7, 15), "Mid Year"),
        ("2025-Anual", dt.date(2025, 12, 10), "Anual"),
        ("2026-MidYear", dt.date(2026, 7, 15), "Mid Year"),
    ]
    n_hitos = len(hitos)
    filas = []
    for r in df.itertuples():
        ingreso = dt.date.fromisoformat(r.fecha_ingreso)
        fin = _fecha_fin(r)
        for idx, (ciclo, fecha, tipo) in enumerate(hitos):
            # Requiere al menos 4 meses en la compañía al momento del hito
            if fecha > fin or (fecha - ingreso).days < 120:
                continue
            eng = engagement(r, idx, n_hitos)
            objetivos = _nota(eng)
            valores = _nota(eng * 0.85 + 0.12, 0.22)   # los valores correlacionan pero menos
            final = round(0.6 * objetivos + 0.4 * valores, 2)
            if final < 3.0:
                cat = "Bajo lo esperado"
            elif final < 3.5:
                cat = "Cumple lo esperado"
            else:
                cat = "Sobresaliente"
            filas.append({
                "employee_id": r.employee_id,
                "ciclo": ciclo, "tipo_ciclo": tipo,
                "fecha_evaluacion": fecha.isoformat(),
                "score_objetivos": round(objetivos, 2),
                "score_valores": round(valores, 2),
                "score_final": final,
                "categoria": cat,
                "tiene_plan_de_accion": bool(final < 3.0 and tipo == "Anual"),
                "evaluador_id": r.manager_id,
            })
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# 6. Métricas operativas mensuales
# ---------------------------------------------------------------------------
MESES_VENTANA = 18  # el Sheet operativo conserva 18 meses de historia


def generar_metricas_operativas(df: pd.DataFrame) -> pd.DataFrame:
    periodos = _meses(AS_OF, MESES_VENTANA)
    inicio_ventana = dt.date.fromisoformat(periodos[0] + "-01")
    filas = []

    for r in df.itertuples():
        ingreso = dt.date.fromisoformat(r.fecha_ingreso)
        fin = _fecha_fin(r)
        cara_cliente = r.job_family in rd.FAMILIAS_CARA_CLIENTE
        dias_sin_vacaciones = int(rng.integers(20, 200))

        for idx, periodo in enumerate(periodos):
            primero = dt.date.fromisoformat(periodo + "-01")
            # Solo meses en que la persona estuvo efectivamente trabajando
            if primero < max(ingreso + dt.timedelta(days=30), inicio_ventana) or primero > fin:
                continue
            eng = engagement(r, idx, MESES_VENTANA)

            # Vacaciones: con política ilimitada, quien está desganado tiende a
            # NO tomarlas. El contador acumulado es el proxy de desgaste.
            if rng.random() < 0.045 + 0.14 * eng:
                dias_sin_vacaciones = int(rng.integers(0, 12))
            else:
                dias_sin_vacaciones += 30

            fila = {
                "employee_id": r.employee_id,
                "periodo": periodo,
                "productividad_pct": round(float(np.clip(
                    62 + 48 * eng + r.prod_intercepto + rng.normal(0, 2.6), 30, 145)), 1),
                "dias_sin_vacaciones": min(dias_sin_vacaciones, 730),
            }
            if cara_cliente:
                fila["csat"] = round(float(np.clip(
                    2.55 + 2.30 * eng + r.csat_intercepto + rng.normal(0, 0.16), 1, 5)), 2)
                fila["nps_proceso"] = int(np.clip(
                    -45 + 135 * eng + 45 * r.csat_intercepto + rng.normal(0, 7), -100, 100))
            else:
                fila["csat"] = None
                fila["nps_proceso"] = None
            filas.append(fila)
    return pd.DataFrame(filas)


def ensuciar_metricas(limpio: pd.DataFrame) -> pd.DataFrame:
    """Degrada la tabla a la calidad real de una planilla mantenida a mano.

    No es un adorno: la JD del cargo pide explícitamente garantizar la validez de
    la información "a través de la limpieza de las bases de datos". Si la fuente
    llega perfecta, la capa de calidad del pipeline no se puede demostrar.
    """
    df = limpio.copy()
    n = len(df)
    # Una planilla mantenida a mano no tiene tipos: todo es texto mezclado.
    for col in ("productividad_pct", "csat", "nps_proceso", "employee_id"):
        df[col] = df[col].astype(object)

    # 1. Formatos de fecha inconsistentes (tres convenciones conviviendo)
    MES_ES = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
              7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}
    estilo = rng.choice([0, 1, 2], size=n, p=[0.72, 0.18, 0.10])
    nuevos = []
    for periodo, e in zip(df.periodo, estilo):
        a, m = periodo.split("-")
        nuevos.append(periodo if e == 0 else
                      (f"{MES_ES[int(m)]}-{a}" if e == 1 else f"{m}/{a}"))
    df["periodo"] = nuevos

    # 2. Nulos escritos a mano de tres formas distintas
    for col, tasa in (("csat", 0.05), ("nps_proceso", 0.05), ("productividad_pct", 0.018)):
        idx = rng.choice(n, size=int(n * tasa), replace=False)
        df.loc[df.index[idx], col] = rng.choice(["N/A", "s/i", "-"], size=len(idx))
    df["csat"] = df.csat.fillna("")
    df["nps_proceso"] = df.nps_proceso.fillna("")

    # 3. Decimales con coma (locale es-CL escrito a mano)
    idx = rng.choice(n, size=int(n * 0.035), replace=False)
    df.loc[df.index[idx], "productividad_pct"] = [
        str(v).replace(".", ",") for v in df.loc[df.index[idx], "productividad_pct"]
    ]

    # 4. Espacios espurios en la clave de cruce
    idx = rng.choice(n, size=int(n * 0.02), replace=False)
    df.loc[df.index[idx], "employee_id"] = [f" {v} " for v in df.loc[df.index[idx], "employee_id"]]

    # 5. Valores imposibles: el contrato de datos debe atraparlos
    idx = rng.choice(n, size=28, replace=False)
    df.loc[df.index[idx[:14]], "productividad_pct"] = 999
    df.loc[df.index[idx[14:]], "csat"] = 0

    # 6. Filas duplicadas por copiar y pegar
    dup = df.sample(int(n * 0.012), random_state=SEMILLA)
    df = pd.concat([df, dup], ignore_index=True).sample(frac=1, random_state=SEMILLA)

    # 7. Encabezados como los escribe una persona, no un sistema
    return df.rename(columns={
        "employee_id": "ID Colaborador", "periodo": "Mes ",
        "productividad_pct": "Productividad %", "csat": "CSAT (1-5)",
        "nps_proceso": "NPS del proceso", "dias_sin_vacaciones": "Días sin vacaciones",
    })


# ---------------------------------------------------------------------------
# 7. Desarrollo (Buk University) y bitácora de seguimiento
# ---------------------------------------------------------------------------
def generar_cursos(df: pd.DataFrame) -> pd.DataFrame:
    inicio = dt.date.fromisoformat(_meses(AS_OF, MESES_VENTANA)[0] + "-01")
    filas = []
    for r in df.itertuples():
        fin = _fecha_fin(r)
        desde = max(dt.date.fromisoformat(r.fecha_ingreso), inicio)
        if fin <= desde:
            continue
        eng_medio = float(np.clip(r.eng_base + r.eng_pendiente * MESES_VENTANA / 2, 0.03, 0.99))
        meses_obs = (fin - desde).days / 30.44

        # El conteo tiene que ser una TASA por tiempo observado, no un total por
        # persona. Repartir un total fijo entre ingreso y salida le daba a quien
        # se fue temprano la misma cantidad de cursos en menos meses, y por lo
        # tanto una densidad mensual más alta: el dato terminaba diciendo que
        # formarse mucho predice renunciar. Era un artefacto del generador, no
        # una relación. Vale como recordatorio de que una métrica acumulada sin
        # denominador de tiempo casi siempre está midiendo otra cosa.
        n = int(rng.poisson((0.45 + 2.8 * eng_medio) * meses_obs / 12))

        # Onboarding: la formación se concentra de verdad en los primeros meses.
        # Este sí es un efecto real, y es la razón por la que las reglas comparan
        # formación contra la cohorte de antigüedad y no en bruto.
        ingreso = dt.date.fromisoformat(r.fecha_ingreso)
        onb_fin = min(fin, ingreso + dt.timedelta(days=210))
        onb_ini = max(desde, ingreso)
        if onb_fin > onb_ini:
            n += int(rng.poisson(2.4 * (onb_fin - onb_ini).days / 210))

        n = min(n, len(rd.CURSOS_BUK_UNIVERSITY))
        for curso in rng.choice(rd.CURSOS_BUK_UNIVERSITY, size=n, replace=False):
            # Los cursos de onboarding caen dentro de la ventana de onboarding.
            if onb_fin > onb_ini and rng.random() < 0.45:
                ini, term = onb_ini, onb_fin
            else:
                ini, term = desde, fin
            fecha = ini + dt.timedelta(days=int(rng.integers(0, max(1, (term - ini).days))))
            filas.append({
                "employee_id": r.employee_id, "curso": str(curso),
                "fecha_finalizacion": fecha.isoformat(),
                "horas": int(rng.choice([2, 4, 6, 8, 12, 16])),
                "plataforma": "Buk University",
            })
    return pd.DataFrame(filas)


# Temas que cada perfil latente tiende a plantear en sus conversaciones
TEMAS_POR_PERFIL = {
    "deterioro": ["carga_trabajo", "relacion_con_lider", "reconocimiento",
                  "balance_vida_trabajo", "clima_equipo", "cambio_organizacional"],
    "estrella_subpagada": ["compensacion", "desarrollo_carrera", "movilidad_interna",
                           "reconocimiento"],
    "nuevo_dificil": ["onboarding", "claridad_rol", "relacion_con_lider", "herramientas_procesos"],
    "bajo_desempeno": ["claridad_rol", "relacion_con_lider", "herramientas_procesos",
                       "desarrollo_carrera"],
    "estable": rd.CURSOS_BUK_UNIVERSITY and tx.TEMAS,
}


def _tono(eng: float) -> str:
    if eng >= 0.72:
        return str(_elige(["pos", "neu", "neg"], [0.62, 0.32, 0.06]))
    if eng >= 0.52:
        return str(_elige(["pos", "neu", "neg"], [0.18, 0.55, 0.27]))
    return str(_elige(["pos", "neu", "neg"], [0.04, 0.26, 0.70]))


def _componer_nota(perfil: str, eng: float) -> tuple[str, str, list[str]]:
    """Compone una nota de bitácora verosímil. Devuelve (texto, tono, temas)."""
    tono = _tono(eng)
    candidatos = TEMAS_POR_PERFIL.get(perfil, tx.TEMAS)
    n_temas = int(_elige([1, 2, 3], [0.24, 0.52, 0.24]))
    temas = list(rng.choice(candidatos, size=min(n_temas, len(candidatos)), replace=False))

    partes = [str(_elige(tx.APERTURAS))]
    for t in temas:
        partes.append(str(_elige(tx.BLOQUES[t][tono])))
    if rng.random() < 0.82:
        partes.append(str(_elige(tx.CONTEXTO[tono])))
    partes.append(str(_elige(tx.CIERRES[tono])))

    texto = " ".join(partes)
    texto = texto.replace("{nombre}", str(_elige(tx.NOMBRES_EN_TEXTO)))
    texto = texto.replace("{cliente}", str(_elige(tx.CLIENTES_EN_TEXTO)))
    return texto, tono, [str(t) for t in temas]


def generar_bitacora(df: pd.DataFrame) -> pd.DataFrame:
    """Registros de la bitácora: el nombre interno que Buk le da a estas notas."""
    periodos = _meses(AS_OF, MESES_VENTANA)
    inicio = dt.date.fromisoformat(periodos[0] + "-01")
    hrbps = [f"hrbp.{n.lower()}@buk.example" for n in
             ("valeria", "ignacia", "matias", "renata", "joaquin", "amanda")]
    filas = []

    for r in df.itertuples():
        fin = _fecha_fin(r)
        desde = max(dt.date.fromisoformat(r.fecha_ingreso) + dt.timedelta(days=45), inicio)
        if fin <= desde:
            continue
        n = int(np.clip(rng.poisson(2.6) + 1, 1, 7))
        for _ in range(n):
            fecha = desde + dt.timedelta(days=int(rng.integers(0, (fin - desde).days)))
            idx_mes = max(0, min(MESES_VENTANA - 1,
                                 (fecha.year - inicio.year) * 12 + fecha.month - inicio.month))
            eng = engagement(r, idx_mes, MESES_VENTANA)
            texto, tono, temas = _componer_nota(r.perfil_latente, eng)
            filas.append({
                "employee_id": r.employee_id,
                "fecha": fecha.isoformat(),
                "autor_hrbp": str(_elige(hrbps)),
                "tipo_instancia": str(_elige(["1:1 Happiness", "Seguimiento post-evaluación",
                                              "Check-in de clima", "Conversación a solicitud"],
                                             [0.48, 0.20, 0.20, 0.12])),
                "nota": texto,
                # Etiquetas "de laboratorio": el pipeline NO las usa. Existen solo
                # para poder medir después qué tan bien las recuperó el modelo.
                "_tono_real": tono,
                "_temas_reales": "|".join(temas),
            })
    return pd.DataFrame(filas).sort_values(["employee_id", "fecha"])


# ---------------------------------------------------------------------------
# 8. Escritura de las fuentes en sus formatos nativos
# ---------------------------------------------------------------------------
# Columnas que existen solo dentro del laboratorio. NUNCA se escriben en las
# fuentes que consume el pipeline: si el pipeline pudiera ver el perfil latente,
# la demo sería una tautología. Se guardan aparte para poder medir después.
COLS_LATENTES = ["perfil_latente", "eng_base", "eng_pendiente", "declive_meses",
                 "idx_ancla", "prod_intercepto", "csat_intercepto", "fecha_salida_dt"]

COLS_DIRECTORIO = [
    "employee_id", "nombre", "email", "genero", "fecha_nacimiento", "nacionalidad",
    "pais_contrato", "pais_residencia", "modalidad", "area", "cargo", "job_family",
    "job_level", "es_liderazgo", "fecha_ingreso", "tipo_contrato",
    "situacion_discapacidad", "diversidad_sexual_declarada", "manager_id", "estado",
]


def escribir(df, salidas, comp, ev90, evd, metricas_sucias, cursos, bitacora):
    CRUDO.mkdir(parents=True, exist_ok=True)

    # --- Tablas BigQuery -> CSV --------------------------------------------
    # El directorio NO lleva datos salariales: viven en su propia tabla, con su
    # propio control de acceso. Separar la fuente sensible es gobernanza, no estilo.
    df[COLS_DIRECTORIO].to_csv(CRUDO / "bq_directorio_personas.csv", index=False)
    comp.to_csv(CRUDO / "bq_compensaciones.csv", index=False)
    ev90.to_csv(CRUDO / "bq_evaluaciones_90d.csv", index=False)
    evd.to_csv(CRUDO / "bq_evaluaciones_desempeno.csv", index=False)
    pd.DataFrame(rd.dim_cargos()).to_csv(CRUDO / "dim_cargos.csv", index=False)

    # --- Planillas Google Sheets -> XLSX -----------------------------------
    metricas_sucias.to_excel(CRUDO / "gs_metricas_operativas.xlsx",
                             sheet_name="Métricas mensuales", index=False)

    publicas = ["employee_id", "fecha", "autor_hrbp", "tipo_instancia", "nota"]
    with pd.ExcelWriter(CRUDO / "gs_desarrollo_bitacora.xlsx") as xl:
        cursos.to_excel(xl, sheet_name="Cursos Buk University", index=False)
        bitacora[publicas].to_excel(xl, sheet_name="Bitácora", index=False)

    salidas.to_excel(CRUDO / "gs_historico_salidas.xlsx",
                     sheet_name="Desvinculaciones", index=False)

    # --- Verdad latente: solo para validar, nunca para decidir -------------
    lab = CRUDO.parent / "laboratorio"
    lab.mkdir(exist_ok=True)
    df[["employee_id"] + COLS_LATENTES].to_csv(lab / "_verdad_latente.csv", index=False)
    bitacora[["employee_id", "fecha", "_tono_real", "_temas_reales"]].to_csv(
        lab / "_bitacora_etiquetas.csv", index=False)


def main() -> None:
    print(f"Generando universo sintético  ·  corte {AS_OF}  ·  semilla {SEMILLA}")
    df = marcar_desvinculados(asignar_perfiles(construir_poblacion()))
    salidas = generar_salidas(df)
    df = anclar_trayectorias(df)
    comp = generar_compensaciones(df)
    ev90 = generar_eval_90d(df)
    evd = generar_eval_desempeno(df)
    metricas = generar_metricas_operativas(df)
    sucias = ensuciar_metricas(metricas)
    cursos = generar_cursos(df)
    bitacora = generar_bitacora(df)

    escribir(df, salidas, comp, ev90, evd, sucias, cursos, bitacora)

    activos = int((df.estado == "Activo").sum())
    print(f"""
  bq_directorio_personas.csv     {len(df):>6} personas ({activos} activas)
  bq_compensaciones.csv          {len(comp):>6} filas
  bq_evaluaciones_90d.csv        {len(ev90):>6} evaluaciones de 90 días
  bq_evaluaciones_desempeno.csv  {len(evd):>6} evaluaciones (escala 1-4)
  dim_cargos.csv                 {len(rd.dim_cargos()):>6} combinaciones cargo x país
  gs_metricas_operativas.xlsx    {len(sucias):>6} filas mensuales  <- con suciedad inyectada
  gs_desarrollo_bitacora.xlsx    {len(cursos):>6} cursos / {len(bitacora)} notas de bitácora
  gs_historico_salidas.xlsx      {len(salidas):>6} desvinculaciones (24 meses)

  Escrito en {CRUDO}""")


if __name__ == "__main__":
    main()
