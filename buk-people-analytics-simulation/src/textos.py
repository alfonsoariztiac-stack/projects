"""
Banco de texto sintético para la bitácora de seguimiento y las entrevistas de salida.

Las notas se componen por bloques (apertura + tema principal + tema secundario +
cierre) para producir cientos de variantes verosímiles. No es lorem ipsum: el
objetivo es que la extracción de temas y sentimiento con un LLM sea una
demostración real, no un truco.

TEMAS es un enum CERRADO. Es la misma lista que se le impone al modelo como
esquema de salida: sin vocabulario controlado, las categorías del LLM derivan en
el tiempo y dejan de ser agregables. Eso es un requisito de gobernanza, no un
detalle de implementación.
"""

TEMAS = [
    "carga_trabajo", "reconocimiento", "desarrollo_carrera", "compensacion",
    "relacion_con_lider", "claridad_rol", "herramientas_procesos", "clima_equipo",
    "balance_vida_trabajo", "movilidad_interna", "cambio_organizacional", "onboarding",
]

# Nombres ficticios que aparecen DENTRO del texto de las notas. Existen para que
# el scrubber de PII tenga algo real que redactar antes de enviar al modelo.
NOMBRES_EN_TEXTO = [
    "Camila", "Matías", "Javiera", "Sebastián", "Fernanda", "Rodrigo", "Antonia",
    "Diego", "Valentina", "Ignacio", "Catalina", "Tomás", "Paula", "Andrés",
    "Josefa", "Cristóbal", "Daniela", "Felipe", "Isidora", "Nicolás",
]
CLIENTES_EN_TEXTO = [
    "Andes Retail", "Grupo Marítimo", "Constructora Sur", "Clínica Los Robles",
    "Transportes Bío", "Alimentos del Valle", "Farmacias Vitalis", "Textil Aurora",
]

APERTURAS = [
    "Conversamos en el 1:1 mensual.",
    "Café de seguimiento, sin agenda formal.",
    "Instancia de seguimiento posterior al cierre de OKRs del trimestre.",
    "Nos juntamos a raíz de la última encuesta de clima del equipo.",
    "Seguimiento agendado por la líder tras el mid year feedback.",
    "Conversación de seguimiento a solicitud del propio buker.",
    "Check-in de rutina del ciclo de Happiness.",
    "Conversación breve después de la reunión de área.",
]

# Bloques por tema y por tono. tono: "pos" | "neu" | "neg"
BLOQUES = {
    "carga_trabajo": {
        "pos": ["Comenta que la carga se estabilizó después de la redistribución del equipo y que hoy alcanza a cerrar sus temas dentro del horario.",
                "Dice que el volumen es alto pero manejable, y que le acomoda el ritmo actual."],
        "neu": ["Menciona que la carga sube fuerte en cierres de mes y baja el resto, pero que ya lo tiene incorporado.",
                "Reporta un volumen de trabajo por sobre lo habitual, asociado a la temporada."],
        "neg": ["Relata que lleva varios meses cubriendo dos frentes tras la salida de {nombre} y que no ve cuándo se repone el cupo.",
                "Señala que las últimas seis semanas ha estado trabajando fuera de horario de forma sistemática para no atrasar entregas.",
                "Describe una carga sostenida que le impide tomar los espacios de foco; dice sentirse 'apagando incendios' todo el día."],
    },
    "reconocimiento": {
        "pos": ["Destaca que su líder reconoció públicamente el trabajo del último release en la reunión de área.",
                "Se muestra contento con el reconocimiento recibido tras el cierre del proyecto con {cliente}."],
        "neu": ["Comenta que el reconocimiento en su equipo tiende a ser informal, y que le acomoda así.",
                "No plantea el reconocimiento como un tema relevante para él en este momento."],
        "neg": ["Plantea que el proyecto con {cliente} lo sacó adelante prácticamente solo y que eso no se visibilizó en ninguna instancia.",
                "Dice que hace tiempo no recibe feedback positivo y que no tiene claridad de si su trabajo se está valorando.",
                "Menciona con molestia que el mérito del último cierre se atribuyó al equipo completo sin mención a quienes lo empujaron."],
    },
    "desarrollo_carrera": {
        "pos": ["Está entusiasmado con el plan de formación que armó con su líder para el próximo semestre.",
                "Terminó dos rutas de Buk University y quiere seguir profundizando en la especialidad."],
        "neu": ["Conversamos sobre posibles rutas de desarrollo; todavía no tiene una definición.",
                "Le interesa el desarrollo técnico pero prefiere consolidarse en el rol actual antes de moverse."],
        "neg": ["Manifiesta que lleva más de dos años en el mismo nivel y que no tiene visibilidad de cuál sería el siguiente paso.",
                "Dice que ve a pares con menos tiempo avanzando y que no entiende con qué criterio se decide.",
                "Comenta que dejó de inscribirse en cursos porque no siente que aporten a un camino concreto."],
    },
    "compensacion": {
        "pos": ["Se mostró conforme con el último ajuste y valora la transparencia con que se le explicó la banda.",
                "Valora especialmente las stock options y la flexibilidad por sobre el componente monetario."],
        "neu": ["Consultó cómo funciona la banda salarial de su cargo; se le explicó el modelo.",
                "Pregunta por el calendario de revisión de rentas del próximo ciclo."],
        "neg": ["Plantea directamente que su renta quedó atrás respecto del mercado y que ha recibido acercamientos externos.",
                "Dice que lleva más de un año sin ajuste pese a haber asumido responsabilidades adicionales.",
                "Comenta que supo de una contratación reciente en su mismo nivel con una renta mayor y que eso le generó ruido."],
    },
    "relacion_con_lider": {
        "pos": ["Describe una relación muy buena con su líder, con feedback frecuente y directo.",
                "Valora el espacio que le da {nombre} para tomar decisiones sin microgestión."],
        "neu": ["La relación con su líder es correcta; los 1:1 se realizan pero de forma irregular.",
                "Comenta que con el cambio de líder recién están calibrando la forma de trabajo."],
        "neg": ["Señala que desde el cambio de líder los 1:1 se suspendieron y que hoy no tiene con quién revisar prioridades.",
                "Describe una relación tensa con su líder: dice que el feedback llega tarde y en tono correctivo.",
                "Comenta que no se siente cómodo planteando desacuerdos en su equipo."],
    },
    "claridad_rol": {
        "pos": ["Tiene claridad de sus objetivos del semestre y cómo se miden.",
                "Comenta que la definición del rol quedó mucho más nítida después del último ajuste de estructura."],
        "neu": ["Conversamos sobre el alcance de su rol; quedaron algunos bordes por definir con su líder.",
                "Le hace sentido su objetivo anual aunque le cuesta traducirlo a métricas semanales."],
        "neg": ["Dice que no tiene claro qué se espera de él este semestre y que sus OKRs no se han revisado desde marzo.",
                "Plantea que hay superposición entre su rol y el de {nombre}, y que eso genera fricción innecesaria.",
                "Comenta que le piden cosas de tres frentes distintos sin un criterio de priorización."],
    },
    "herramientas_procesos": {
        "pos": ["Destaca la mejora en el proceso de handoff con el equipo de implementación.",
                "Comenta que las automatizaciones nuevas le liberaron varias horas a la semana."],
        "neu": ["Menciona fricciones menores con algunas herramientas internas, nada bloqueante.",
                "Sugiere ajustes al proceso de documentación del área."],
        "neg": ["Describe que buena parte de su semana se va en trabajo manual que debería estar automatizado.",
                "Plantea que la falta de un proceso claro de escalamiento lo deja expuesto frente al cliente."],
    },
    "clima_equipo": {
        "pos": ["Habla muy bien del clima del equipo y de la cercanía con sus pares.",
                "Valora las actividades de Happiness del último trimestre; dice que ayudaron a soltar tensión."],
        "neu": ["El clima del equipo le parece normal; sin temas relevantes que reportar.",
                "Comenta que el equipo está en un momento de mucha exigencia pero con buena disposición."],
        "neg": ["Describe un clima tenso en el equipo tras las últimas salidas, con conversaciones de pasillo sobre quién sigue.",
                "Comenta que se siente aislado del resto del equipo desde que pasó a trabajar full remoto."],
    },
    "balance_vida_trabajo": {
        "pos": ["Aprovechó la política de vacaciones para tomarse dos semanas y volvió con mucha mejor energía.",
                "Valora enormemente el WFA; está trabajando desde el sur y le ha resultado muy bien."],
        "neu": ["Conversamos sobre sus tiempos de descanso; dice tenerlos razonablemente cubiertos.",
                "Planea tomar vacaciones en el próximo trimestre, aún sin fecha."],
        "neg": ["Reconoce que no toma vacaciones hace casi un año porque 'no es el momento' del equipo.",
                "Comenta que le cuesta desconectar y que ha estado respondiendo mensajes los fines de semana.",
                "Se le nota cansado; dice que hace tiempo no tiene un fin de semana sin pendientes."],
    },
    "movilidad_interna": {
        "pos": ["Postuló a un movimiento interno y está muy motivado con la posibilidad.",
                "Le entusiasma la opción de rotar hacia otro equipo el próximo año."],
        "neu": ["Exploramos si le interesaría un movimiento interno; lo está pensando.",
                "Sabe que existen concursos internos pero no ha postulado."],
        "neg": ["Postuló a dos procesos internos y en ninguno recibió retroalimentación; dice que eso lo desanimó.",
                "Siente que la movilidad interna en su área está bloqueada porque no se abren cupos."],
    },
    "cambio_organizacional": {
        "pos": ["El cambio de estructura le resultó positivo: quedó más cerca de las decisiones de producto.",
                "Comenta que la nueva organización del área le dio más autonomía."],
        "neu": ["Está adaptándose al cambio de estructura del área; sin mayores complicaciones.",
                "Menciona el reciente cambio organizacional como un tema en curso."],
        "neg": ["Dice que en los últimos doce meses cambió tres veces de líder y que cada vez parte de cero.",
                "Plantea incertidumbre por la reestructuración del área y no sabe dónde queda su rol."],
    },
    "onboarding": {
        "pos": ["Muy buena evaluación del onboarding: dice que llegó con todo listo y con un buddy asignado.",
                "Destaca lo rápido que se sintió parte del equipo."],
        "neu": ["El onboarding fue correcto; le faltó algo de contexto de negocio pero lo fue supliendo.",
                "Todavía está calibrando expectativas propias del período de adaptación."],
        "neg": ["Comenta que llegó sin accesos durante las primeras dos semanas y que eso le costó tomar ritmo.",
                "Dice que el rol que está haciendo no se parece al que le describieron en el proceso de selección.",
                "Refiere dificultad para conectar con el equipo; siente que le falta acompañamiento en esta etapa."],
    },
}

# Detalle de contexto que un HRBP anota casi siempre: dato duro, antecedente o
# matiz. Alarga la nota hasta un largo realista y le da material concreto al
# modelo para citar como evidencia.
CONTEXTO = {
    "pos": [
        "Viene de cerrar un trimestre por sobre meta y se le nota tranquilo.",
        "Es la segunda conversación seguida en que aparece este punto en positivo.",
        "Su líder lo había anticipado en el comité de calibración.",
        "Mencionó de paso que recomendó a un conocido para una vacante del área.",
        "Lleva tres rutas de Buk University terminadas este semestre.",
    ],
    "neu": [
        "No hay antecedentes previos de este tema en su bitácora.",
        "Es primera vez que lo plantea en una instancia formal.",
        "Coincide con el período de cierre trimestral del área.",
        "Su líder está al tanto y lo viene conversando con él.",
        "Quedamos de retomarlo cuando esté cerrado el ciclo en curso.",
    ],
    "neg": [
        "Es la tercera conversación consecutiva en que aparece el mismo punto.",
        "Ya lo había planteado en la instancia anterior y no hubo cambios.",
        "Se le nota más distante que en conversaciones previas; respuestas breves.",
        "Evitó comprometerse con plazos cuando le pregunté por sus objetivos del semestre.",
        "Es la primera vez que menciona explícitamente estar mirando otras opciones.",
        "Coincide con la caída que veníamos observando en sus indicadores del área.",
    ],
}

CIERRES = {
    "pos": ["Queda de compartir lo aprendido con el resto del equipo.",
            "Sin acciones pendientes de mi parte; se retoma en el próximo ciclo.",
            "Acordamos mantener la cadencia mensual."],
    "neu": ["Acordamos retomar el tema en la próxima instancia.",
            "Queda pendiente conversarlo con su líder.",
            "Sin acciones inmediatas; se deja registro para seguimiento."],
    "neg": ["Se compromete a levantarlo con su líder; le ofrecí acompañar esa conversación.",
            "Acordamos volver a revisarlo en dos semanas.",
            "Le pedí que no lo deje pasar; quedo atenta a cómo evoluciona.",
            "Queda con la sensación de no ser escuchado. Requiere seguimiento cercano."],
}

# --- Entrevistas de salida --------------------------------------------------
MOTIVOS_SALIDA_VOLUNTARIA = [
    "Mejor oferta económica", "Cambio de rubro o proyecto personal",
    "Falta de oportunidades de desarrollo", "Relación con la jefatura",
    "Carga de trabajo y desgaste", "Motivos personales o familiares",
    "Traslado de ciudad o país", "Continuar estudios",
]
MOTIVOS_SALIDA_INVOLUNTARIA = [
    "Desempeño bajo lo esperado", "Reestructuración del área",
    "Término de proyecto", "No superación del período de prueba",
]

SALIDA_TEXTO = {
    "Mejor oferta económica": "Recibió una oferta con una renta significativamente mayor. Menciona que había planteado el tema de banda internamente y que la respuesta se demoró más de lo que esperaba. Se va en buenos términos y destaca al equipo.",
    "Cambio de rubro o proyecto personal": "Decidió tomar un camino distinto fuera del rubro. Evalúa bien su paso por Buk y destaca la cultura del equipo. No hay temas pendientes.",
    "Falta de oportunidades de desarrollo": "Señala que no logró visualizar un siguiente paso en su carrera dentro del área. Postuló a movimientos internos sin recibir retroalimentación. Es el punto que más pesó en su decisión.",
    "Relación con la jefatura": "Refiere una relación difícil con su jefatura directa, con feedback poco frecuente y en tono correctivo. Dice haberlo mencionado en instancias previas sin cambios visibles.",
    "Carga de trabajo y desgaste": "Describe un período prolongado de sobrecarga tras la salida de dos personas del equipo que no fueron repuestas. Reconoce no haber tomado vacaciones en el último año.",
    "Motivos personales o familiares": "Sale por razones personales ajenas al trabajo. Evaluación positiva de su experiencia; dejaría la puerta abierta a volver más adelante.",
    "Traslado de ciudad o país": "Se traslada por razones familiares y el rol no era compatible con la nueva zona horaria. Buena evaluación general.",
    "Continuar estudios": "Inicia un programa de posgrado a tiempo completo. Evaluación positiva de su paso por la compañía.",
    "Desempeño bajo lo esperado": "Cierre del plan de acción sin alcanzar las metas comprometidas. Se realizó el proceso con acompañamiento del líder y del área de Personas.",
    "Reestructuración del área": "Su posición se elimina en el rediseño del área. Sin observaciones sobre el desempeño de la persona.",
    "Término de proyecto": "Cierre del proyecto para el cual fue contratado. Sin observaciones.",
    "No superación del período de prueba": "No se alcanzó el ajuste esperado al rol durante los primeros meses. Se documentó en la evaluación de 90 días.",
}
