"""
Catálogos dimensionales del universo sintético.

Todo lo que aquí se define es la "estructura organizacional" contra la que se
evalúan las reglas de negocio. Vive separado del generador y del motor de reglas
a propósito: si mañana cambia la estructura de cargos, se cambia este archivo
(o la tabla dim_cargos que produce) y nada más.
"""

# --- Países donde Buk tiene entidad legal -----------------------------------
# Determinan moneda, banda salarial y legislación. NO son la nacionalidad de la
# persona: Buk declara +20 nacionalidades trabajando desde todo el mundo (WFA).
PAISES_CONTRATO = {
    # código: (nombre, moneda, año de apertura, peso en la dotación, factor de mercado vs Chile)
    "CL": ("Chile", "CLP", 2017, 0.54, 1.00),
    "CO": ("Colombia", "COP", 2019, 0.13, 0.75),
    "PE": ("Perú", "PEN", 2020, 0.10, 0.80),
    "MX": ("México", "MXN", 2022, 0.16, 0.95),
    "BR": ("Brasil", "BRL", 2025, 0.07, 0.90),
}

# Tipo de cambio a CLP (referencial, agosto 2026). Se usa solo para derivar las
# bandas locales desde una escala común; los sueldos se expresan en moneda local.
FX_A_CLP = {"CLP": 1.0, "COP": 0.23, "PEN": 255.0, "MXN": 50.0, "BRL": 175.0}

# --- Nacionalidades ---------------------------------------------------------
# Atributo PROTEGIDO: nunca entra como condición de una regla. Solo se usa para
# auditar impacto dispar (pilar "Diversidad Cultural" de la política D&I de Buk).
NACIONALIDADES = [
    ("Chilena", 0.335), ("Colombiana", 0.115), ("Peruana", 0.095),
    ("Mexicana", 0.130), ("Brasileña", 0.060), ("Argentina", 0.055),
    ("Venezolana", 0.055), ("Ecuatoriana", 0.020), ("Boliviana", 0.015),
    ("Uruguaya", 0.013), ("Paraguaya", 0.008), ("Costarricense", 0.007),
    ("Guatemalteca", 0.006), ("Dominicana", 0.006), ("Cubana", 0.005),
    ("Española", 0.021), ("Italiana", 0.012), ("Francesa", 0.008),
    ("Alemana", 0.007), ("Portuguesa", 0.006), ("Británica", 0.005),
    ("Estadounidense", 0.008), ("Canadiense", 0.005),
    ("Australiana", 0.002), ("Neozelandesa", 0.001),
]

# --- Arquitectura de cargos -------------------------------------------------
# (familia, área, [cargos], multiplicador de banda vs. la escala base por nivel)
FAMILIAS = {
    "Ingeniería":      ("Tecnología", ["Software Engineer", "QA Engineer", "SRE", "Data Engineer", "Security Engineer"], 1.20),
    "Producto":        ("Tecnología", ["Product Manager", "Product Designer", "UX Researcher"], 1.15),
    "Datos":           ("Tecnología", ["Data Analyst", "Analytics Engineer", "People Analytics"], 1.15),
    "Ventas":          ("Comercial", ["Account Executive", "SDR", "Ejecutivo Comercial"], 1.00),
    "Customer Success":("Comercial", ["Customer Success Manager", "Account Manager", "Especialista de Renovaciones"], 0.90),
    "Soporte":         ("Operaciones", ["Agente de Soporte", "Especialista de Soporte", "Especialista de Soporte Payroll"], 0.75),
    "Implementación":  ("Operaciones", ["Consultor de Implementación", "Project Manager de Implementación"], 0.85),
    "Operaciones":     ("Operaciones", ["Analista de Operaciones", "Especialista Payroll Ops"], 0.80),
    "Marketing":       ("Comercial", ["Growth Marketer", "Content Manager", "Brand Manager"], 0.90),
    "Finanzas":        ("Administración", ["Analista Contable", "Control de Gestión", "Analista de Cobranza"], 0.90),
    "Personas":        ("Administración", ["People Happiness Manager", "Talent Acquisition", "Especialista de Formación"], 0.85),
    "Legal":           ("Administración", ["Abogado Corporativo"], 1.00),
}

# Peso de cada familia en la dotación
PESO_FAMILIA = {
    "Ingeniería": 0.19, "Producto": 0.05, "Datos": 0.04, "Ventas": 0.14,
    "Customer Success": 0.13, "Soporte": 0.12, "Implementación": 0.10,
    "Operaciones": 0.06, "Marketing": 0.05, "Finanzas": 0.05,
    "Personas": 0.05, "Legal": 0.02,
}

# Escala base de bandas: sueldo base mensual mediano en CLP para Chile, nivel puro.
# NIVEL: (etiqueta, mediana CLP, peso en la dotación)
NIVELES = {
    "IC1": ("Aprendiz",        900_000, 0.15),
    "IC2": ("Analista",      1_350_000, 0.28),
    "IC3": ("Semi Senior",   1_900_000, 0.26),
    "IC4": ("Senior",        2_700_000, 0.145),
    "IC5": ("Especialista",  3_600_000, 0.052),
    "M1":  ("Líder",         2_600_000, 0.075),   # Buk declara ~200 líderes sobre ~1.800 bukers
    "M2":  ("Subgerente",    3_800_000, 0.028),
    "M3":  ("Gerente",       5_500_000, 0.010),
}
NIVELES_LIDERAZGO = {"M1", "M2", "M3"}

# Amplitud de la banda alrededor de la mediana (diseño ±20% / +25%)
BANDA_MIN_PCT, BANDA_MAX_PCT = 0.80, 1.25

# Familias con contacto directo con cliente: son las únicas que tienen CSAT/NPS.
FAMILIAS_CARA_CLIENTE = {"Customer Success", "Soporte", "Implementación", "Ventas"}

# --- Cursos de Buk University ----------------------------------------------
CURSOS_BUK_UNIVERSITY = [
    "Fundamentos de Payroll LATAM", "Comunicación efectiva", "Liderazgo horizontal",
    "SQL para no técnicos", "Cultura Buk: modo Beta", "Feedback que construye",
    "Negociación consultiva", "Gestión del tiempo", "Excel avanzado",
    "Inteligencia artificial aplicada al trabajo", "Seguridad de la información",
    "Diversidad e inclusión en el día a día", "Metodologías ágiles",
    "Atención al cliente de excelencia", "Finanzas para no financieros",
]

# --- Perfiles latentes ------------------------------------------------------
# El "modelo causal" del universo sintético. Cada persona recibe un perfil que
# gobierna simultáneamente su desempeño, sus métricas operativas, el tono de su
# bitácora y su probabilidad de salida. Es lo que hace que las reglas encuentren
# señal — y por eso mismo el backtest valida el MÉTODO, no la eficacia real.
PERFILES = {
    "estable":          0.68,  # engagement alto y plano
    "deterioro":        0.12,  # caída sostenida: el caso que el sistema debe ver a tiempo
    "estrella_subpagada": 0.09,  # alto desempeño + compa-ratio bajo (equidad interna)
    "bajo_desempeno":   0.05,  # desempeño bajo la expectativa; ya en canal de líder
    "nuevo_dificil":    0.06,  # onboarding con mal ajuste en los primeros 90 días
}


def banda_salarial(familia: str, nivel: str, pais: str) -> tuple[float, float, float]:
    """Banda (mín, mediana, máx) del cargo en la moneda local del país."""
    mult_familia = FAMILIAS[familia][2]
    base_clp = NIVELES[nivel][1] * mult_familia
    _, moneda, _, _, factor_mercado = PAISES_CONTRATO[pais]
    mediana_local = base_clp * factor_mercado / FX_A_CLP[moneda]
    # Redondeo a la unidad significativa de cada moneda
    paso = {"CLP": 10_000, "COP": 50_000, "PEN": 100, "MXN": 500, "BRL": 100}[moneda]
    med = round(mediana_local / paso) * paso
    return (round(med * BANDA_MIN_PCT / paso) * paso, med,
            round(med * BANDA_MAX_PCT / paso) * paso)


def dim_cargos() -> list[dict]:
    """Tabla dimensional cargo -> (familia, nivel, área) para todos los países.

    Es LA pieza de gobernanza: las reglas de negocio referencian familia y nivel,
    nunca el título del cargo. Un rediseño organizacional se absorbe actualizando
    esta tabla, sin tocar el motor de reglas.
    """
    filas = []
    for familia, (area, cargos, _) in FAMILIAS.items():
        for cargo in cargos:
            for nivel, (etiqueta, _, _) in NIVELES.items():
                es_lider = nivel in NIVELES_LIDERAZGO
                # Los cargos de liderazgo se nombran distinto
                if es_lider:
                    titulo = f"{etiqueta} de {familia}"
                else:
                    titulo = f"{cargo} {etiqueta}" if etiqueta != "Analista" else cargo
                for pais in PAISES_CONTRATO:
                    b_min, b_med, b_max = banda_salarial(familia, nivel, pais)
                    filas.append({
                        "cargo": titulo, "job_family": familia, "job_level": nivel,
                        "etiqueta_nivel": etiqueta, "area": area,
                        "pais_contrato": pais, "moneda": PAISES_CONTRATO[pais][1],
                        "banda_min": b_min, "banda_med": b_med, "banda_max": b_max,
                        "es_liderazgo": es_lider,
                    })
    # Deduplicar: los cargos de liderazgo colapsan a un solo título por familia/nivel
    vistos, unicas = set(), []
    for f in filas:
        clave = (f["cargo"], f["pais_contrato"])
        if clave not in vistos:
            vistos.add(clave)
            unicas.append(f)
    return unicas
