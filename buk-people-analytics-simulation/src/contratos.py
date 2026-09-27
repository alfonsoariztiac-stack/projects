"""
Contratos de datos: qué se espera de cada fuente antes de dejarla entrar.

El contrato es además una **allowlist**: una columna que no está declarada no
entra al pipeline, aunque venga en el archivo. Por eso `email` no aparece en
ninguna parte de este módulo — existe en el origen y nunca cruza la frontera.
`nombre` sí entra, porque el Happiness Manager necesita saber de quién se le
está hablando, pero se queda en la capa de staging y no llega a employee_360:
se une al final, solo para renderizar la alerta a quien está autorizado a verla.

Un contrato declara clave primaria, columnas obligatorias, tipos y rangos
válidos. El pipeline no "arregla lo que puede y sigue": separa lo que cumple de
lo que no, y deja registro de cada fila descartada y por qué.

El criterio detrás: un dato malo que entra silenciosamente al warehouse termina
en una alerta sobre una persona real. Es preferible una alerta menos que una
alerta construida sobre un valor de productividad de 999%.
"""

ID_BUKER = r"^BUK\d{5}$"

CONTRATOS = {
    "directorio": {
        "archivo": "bq_directorio_personas.csv", "formato": "csv",
        "descripcion": "Directorio de personas (tabla BigQuery)",
        "clave": ["employee_id"],
        "columnas": {
            "employee_id":    {"tipo": "texto", "requerido": True, "patron": ID_BUKER},
            # Necesario para dirigir la alerta; excluido de employee_360.
            "nombre":         {"tipo": "texto", "requerido": True},
            "genero":         {"tipo": "texto", "requerido": True},
            "fecha_nacimiento": {"tipo": "fecha", "requerido": True},
            "nacionalidad":   {"tipo": "texto", "requerido": True},
            "pais_contrato":  {"tipo": "texto", "requerido": True,
                               "valores": ["CL", "PE", "CO", "MX", "BR"]},
            "area":           {"tipo": "texto", "requerido": True},
            "cargo":          {"tipo": "texto", "requerido": True},
            "job_family":     {"tipo": "texto", "requerido": True},
            "job_level":      {"tipo": "texto", "requerido": True},
            "fecha_ingreso":  {"tipo": "fecha", "requerido": True},
            "manager_id":     {"tipo": "texto", "requerido": False, "patron": ID_BUKER},
            "es_liderazgo":   {"tipo": "booleano", "requerido": False},
            "modalidad":      {"tipo": "texto", "requerido": False},
            "pais_residencia": {"tipo": "texto", "requerido": False},
            # Pilares D&I de Buk. Solo para auditar impacto dispar, nunca features.
            "situacion_discapacidad":      {"tipo": "booleano", "requerido": False},
            "diversidad_sexual_declarada": {"tipo": "texto", "requerido": False},
            "estado":         {"tipo": "texto", "requerido": True,
                               "valores": ["Activo", "Desvinculado"]},
        },
    },
    "compensaciones": {
        "archivo": "bq_compensaciones.csv", "formato": "csv",
        "descripcion": "Sueldo base y banda del cargo (tabla BigQuery / reporte Looker)",
        "clave": ["employee_id"],
        "columnas": {
            "employee_id": {"tipo": "texto", "requerido": True, "patron": ID_BUKER},
            "moneda":      {"tipo": "texto", "requerido": True,
                            "valores": ["CLP", "PEN", "COP", "MXN", "BRL"]},
            "sueldo_base": {"tipo": "numero", "requerido": True, "min": 1},
            "banda_min":   {"tipo": "numero", "requerido": True, "min": 1},
            "banda_med":   {"tipo": "numero", "requerido": True, "min": 1},
            "banda_max":   {"tipo": "numero", "requerido": True, "min": 1},
            "compa_ratio": {"tipo": "numero", "requerido": True, "min": 0.3, "max": 2.5},
            "posicion_en_banda": {"tipo": "texto", "requerido": False},
            "fecha_ultimo_ajuste": {"tipo": "fecha", "requerido": False},
            "meses_desde_ultimo_ajuste": {"tipo": "entero", "requerido": True, "min": 0, "max": 120},
            "tiene_incentivo_variable": {"tipo": "booleano", "requerido": False},
        },
    },
    "evaluaciones_90d": {
        "archivo": "bq_evaluaciones_90d.csv", "formato": "csv",
        "descripcion": "Evaluación inicial de 90 días (tabla BigQuery)",
        "clave": ["employee_id"],
        "columnas": {
            "employee_id":      {"tipo": "texto", "requerido": True, "patron": ID_BUKER},
            "fecha_evaluacion": {"tipo": "fecha", "requerido": True},
            # Escala 1-4 de Buk: <3 bajo, 3-3.4 cumple, 3.5-4 sobresaliente
            "score_desempeno":  {"tipo": "numero", "requerido": True, "min": 1, "max": 4},
            "score_adaptacion_cultural": {"tipo": "numero", "requerido": True, "min": 1, "max": 4},
            "recomendacion":    {"tipo": "texto", "requerido": True},
        },
    },
    "evaluaciones_desempeno": {
        "archivo": "bq_evaluaciones_desempeno.csv", "formato": "csv",
        "descripcion": "Ciclo anual + mid year feedback, escala 1-4 (tabla BigQuery)",
        "clave": ["employee_id", "ciclo"],
        "columnas": {
            "employee_id":      {"tipo": "texto", "requerido": True, "patron": ID_BUKER},
            "ciclo":            {"tipo": "texto", "requerido": True},
            "tipo_ciclo":       {"tipo": "texto", "requerido": True,
                                 "valores": ["Anual", "Mid Year"]},
            "fecha_evaluacion": {"tipo": "fecha", "requerido": True},
            "score_objetivos":  {"tipo": "numero", "requerido": True, "min": 1, "max": 4},
            "score_valores":    {"tipo": "numero", "requerido": True, "min": 1, "max": 4},
            "score_final":      {"tipo": "numero", "requerido": True, "min": 1, "max": 4},
            "categoria":        {"tipo": "texto", "requerido": True,
                                 "valores": ["Bajo lo esperado", "Cumple lo esperado", "Sobresaliente"]},
            "tiene_plan_de_accion": {"tipo": "booleano", "requerido": False},
        },
    },
    "metricas_operativas": {
        "archivo": "gs_metricas_operativas.xlsx", "formato": "xlsx",
        "descripcion": "Productividad, CSAT/NPS y vacaciones por mes (Google Sheets)",
        "clave": ["employee_id", "periodo"],
        # La planilla la mantiene una persona: encabezados libres, tipos mezclados.
        "renombrar": {
            "ID Colaborador": "employee_id", "Mes ": "periodo", "Mes": "periodo",
            "Productividad %": "productividad_pct", "CSAT (1-5)": "csat",
            "NPS del proceso": "nps_proceso", "Días sin vacaciones": "dias_sin_vacaciones",
        },
        "columnas": {
            "employee_id":       {"tipo": "texto", "requerido": True, "patron": ID_BUKER},
            "periodo":           {"tipo": "periodo", "requerido": True},
            "productividad_pct": {"tipo": "numero", "requerido": True, "min": 20, "max": 200},
            "csat":              {"tipo": "numero", "requerido": False, "min": 1, "max": 5},
            "nps_proceso":       {"tipo": "entero", "requerido": False, "min": -100, "max": 100},
            "dias_sin_vacaciones": {"tipo": "entero", "requerido": False, "min": 0, "max": 1000},
        },
    },
    "cursos": {
        "archivo": "gs_desarrollo_bitacora.xlsx", "formato": "xlsx",
        "hoja": "Cursos Buk University",
        "descripcion": "Cursos finalizados en Buk University (Google Sheets)",
        "clave": ["employee_id", "curso", "fecha_finalizacion"],
        "columnas": {
            "employee_id":        {"tipo": "texto", "requerido": True, "patron": ID_BUKER},
            "curso":              {"tipo": "texto", "requerido": True},
            "fecha_finalizacion": {"tipo": "fecha", "requerido": True},
            "horas":              {"tipo": "entero", "requerido": False, "min": 0, "max": 200},
        },
    },
    "bitacora": {
        "archivo": "gs_desarrollo_bitacora.xlsx", "formato": "xlsx",
        "hoja": "Bitácora",
        "descripcion": "Notas de seguimiento del HRBP (Google Sheets / Docs)",
        "clave": ["employee_id", "fecha", "autor_hrbp"],
        "columnas": {
            "employee_id":    {"tipo": "texto", "requerido": True, "patron": ID_BUKER},
            "fecha":          {"tipo": "fecha", "requerido": True},
            "autor_hrbp":     {"tipo": "texto", "requerido": True},
            "tipo_instancia": {"tipo": "texto", "requerido": False},
            "nota":           {"tipo": "texto", "requerido": True, "largo_min": 20},
        },
    },
    "salidas": {
        "archivo": "gs_historico_salidas.xlsx", "formato": "xlsx",
        "hoja": "Desvinculaciones",
        "descripcion": "Histórico de desvinculaciones y entrevistas de salida (Google Sheets)",
        "clave": ["employee_id"],
        "columnas": {
            "employee_id":      {"tipo": "texto", "requerido": True, "patron": ID_BUKER},
            "fecha_salida":     {"tipo": "fecha", "requerido": True},
            "tipo_salida":      {"tipo": "texto", "requerido": True,
                                 "valores": ["Voluntaria", "No voluntaria"]},
            "motivo_declarado": {"tipo": "texto", "requerido": True},
            "salida_lamentada": {"tipo": "booleano", "requerido": False},
            "meses_en_buk":     {"tipo": "entero", "requerido": False, "min": 0, "max": 600},
            # Dato sensible: se queda en staging y NUNCA sale crudo del perímetro
            # hacia un modelo de terceros. Ver src/llm/.
            "texto_entrevista_salida": {"tipo": "texto", "requerido": False},
        },
    },
    "dim_cargos": {
        "archivo": "dim_cargos.csv", "formato": "csv",
        "descripcion": "Tabla dimensional cargo -> familia x nivel x banda. LA pieza de gobernanza.",
        "clave": ["cargo", "pais_contrato"],
        "columnas": {
            "cargo":         {"tipo": "texto", "requerido": True},
            "job_family":    {"tipo": "texto", "requerido": True},
            "job_level":     {"tipo": "texto", "requerido": True},
            "etiqueta_nivel": {"tipo": "texto", "requerido": True},
            "area":          {"tipo": "texto", "requerido": True},
            "pais_contrato": {"tipo": "texto", "requerido": True},
            "moneda":        {"tipo": "texto", "requerido": True},
            "banda_min":     {"tipo": "numero", "requerido": True, "min": 1},
            "banda_med":     {"tipo": "numero", "requerido": True, "min": 1},
            "banda_max":     {"tipo": "numero", "requerido": True, "min": 1},
        },
    },
}

# Nulos escritos a mano que hay que reconocer como ausencia de dato
NULOS_TEXTUALES = {"N/A", "n/a", "NA", "s/i", "S/I", "-", "--", "", "nan", "None", "null", "#N/A"}
