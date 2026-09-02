"""
Entrypoint del Cloud Run Job mensual: encadena las 5 fases que ya corren
sueltas a mano, en el orden real de producción. Ninguna se reescribe acá —
job.py solo llama a los `main()` que cada módulo ya expone para uso por CLI.

    1. cargar_bq        -> refresca stg_* leyendo Sheets (raw_*) + los 5 CSV
    2. correr_sql       -> corre src/sql/*.sql sin tocarlos, materializa employee_360
    3. pipeline         -> motor.ejecutar() contra BigQuery, escribe la tabla `alertas`
    4. enriquecer_notas -> notas de bitácora por el LLM, escribe `bitacora_llm`
    5. enviar_chat      -> postea las tarjetas reales al Space (`en_vivo=True`)

`enriquecer_notas` va DESPUÉS de `pipeline`, y el orden es el argumento: solo
lee las notas de las personas que ya tienen una alerta decidida por datos
duros. El texto no puede haber influido en una decisión que ya está tomada, y
además se procesa el mínimo de notas necesario — minimización de datos, no
solo anonimización. El contexto se engancha en la fase 5, al construir la
tarjeta; ninguna regla lo ve. Ver el docstring de `enriquecer_notas.py`.

`cargar_bq` no está entre los tres módulos que pidió el plan original
(correr_sql/pipeline/enviar_chat), pero sin él el job correría el SQL sobre
un `stg_*` congelado en la foto de la última corrida a mano — no sería un job
mensual de verdad. Es también la única fase que toca Drive (F2): por eso el
"riesgo declarado" del plan (que la SA necesita scope de Drive en Cloud Run)
vive exactamente acá, no en las otras tres.

Sin `generate_data` ni backtest/equidad/catalogo: ver README.md, "Qué no
migra" — son auditoría offline, no pasos de un pipeline productivo.

Identidad: el job corre nativamente como la service account `pipeline-alertas`
(`--service-account` en el deploy), así que ninguna llamada de acá pasa
`--impersonar`. La única que sigue impersonando es `cargar_bq.construir()`
internamente, siempre, para pedir el scope de Drive que el token por defecto
del contenedor no trae — impersonarse a sí misma, con
`roles/iam.serviceAccountTokenCreator` concedido sobre su propio email (ver
`README.md`, sección Cloud Run).
"""

from __future__ import annotations

import sys
import time

import cargar_bq
import correr_sql
import enriquecer_notas
import enviar_chat
import pipeline


def main() -> None:
    inicio = time.monotonic()

    print("== 1/5 · cargar_bq: refrescar stg_* (Sheets + CSV) ==")
    cargar_bq.main()

    print("\n== 2/5 · correr_sql: materializar employee_360 ==")
    correr_sql.main()

    print("\n== 3/5 · pipeline: motor de reglas -> tabla alertas ==")
    pipeline.main()

    print("\n== 4/5 · enriquecer_notas: bitácora -> LLM -> bitacora_llm ==")
    enriquecer_notas.main()

    print("\n== 5/5 · enviar_chat: postear tarjetas al Space ==")
    enviar_chat.main(en_vivo=True)

    print(f"\nOK · corrida completa en {time.monotonic() - inicio:,.1f} s")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Cloud Scheduler solo ve el código de salida del job; el traceback
        # completo queda en Cloud Logging igual, pero un exit != 0 explícito
        # es lo que hace que la ejecución se marque como Failed en la consola.
        import traceback
        traceback.print_exc()
        sys.exit(1)
