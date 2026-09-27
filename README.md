# Alfonso Ariztía — Portafolio

Ingeniero de Soluciones IA | Ingeniero Civil Industrial

Ingeniero con experiencia corporativa en analítica de datos e inteligencia de negocios, especializado en agentes de IA y automatización para PYMEs. Fundador de FactIA.

Mi diferenciador: traduzco sistemas técnicos complejos en soluciones que puedo explicar a stakeholders no técnicos.

Este repositorio reúne proyectos reales, de dos tipos:

- **Proyectos con código privado** (App Renaser y Transrai Agent, por acuerdo de confidencialidad con el cliente; Web FactIA, código de mi propia consultora): documentados como case study, con el problema, la solución, el stack y los resultados.
- **Proyectos de código abierto** (MNIST Neural Network, Buk People Analytics Simulation): implementación completa, sin restricciones.

## Proyectos

| Proyecto | Qué es | Estado | Stack destacado |
|---|---|---|---|
| [App Renaser](app-renaser/) | PWA de gestión para un estudio de yoga: reservas, packs de créditos, pagos y panel de administración. | En producción | Next.js, PostgreSQL/Prisma, NextAuth, Mercado Pago |
| [Transrai Agent](transrai-agent/) | Tres agentes de IA que automatizan cerca del 75% de la operación administrativa de una empresa de traslados VIP: leen correos, agendan en Google Calendar y avisan a los choferes, sin que el operador toque nada. | En producción | Python, Claude (Anthropic), Google Calendar/Sheets API, Twilio |
| [Web FactIA](web-factia/) | Landing page de FactIA, con un escenario de datos interactivo y un configurador de servicios, sin backend propio. | En producción | HTML/CSS/JS sin framework, Apache ECharts, Cloudflare Workers |
| [Buk People Analytics Simulation](buk-people-analytics-simulation/) | Sistema de alertas tempranas de People Happiness/RRHH: cruza desempeño, compensación y notas cualitativas (redactadas antes de pasar por un LLM) para detectar riesgo de desvinculación, con un pipeline local en DuckDB replicado 1:1 en GCP (BigQuery + Cloud Run + Cloud Scheduler). | Código abierto (caso práctico) | Python, DuckDB, BigQuery, Cloud Run, Gemini |
| [MNIST Neural Network](mnist-neural-network/) | Red neuronal feedforward para reconocer dígitos escritos a mano, implementada desde cero con NumPy y comparada con una versión en PyTorch: 93.72% y 94.13% de precisión. | Código abierto | Python, NumPy, PyTorch |

## Contacto

- alfonso.ariztia.c@gmail.com
- [LinkedIn](https://www.linkedin.com/in/alfonso-ariztia/)
- [factia.cl](https://factia.cl)
