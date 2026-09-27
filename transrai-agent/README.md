# Transrai Agent

Sistema de agentes de IA que automatiza cerca del 75% de la operación administrativa de Transrai, una empresa de traslados VIP en Santiago. Reemplaza el proceso manual de leer correos, agendar en Google Calendar, registrar estos servicios (y modificaciones de estos) en una planilla y capturar feedback de los conductores. Todo corre solo, 24/7, sin que el operador toque nada.

![Arquitectura del sistema](diagrams/main-diagram.svg)

## El problema

El operador de Transrai (el dueño de la empresa, sin manejo técnico) recibía los correos de los clientes y hacía todo a mano: leer el correo, entender qué pedían, abrir Google Calendar y crear el evento, monitorear el servicio para capturar cualquier desvío o cambio de planes, y registrar el evento en Google Sheets. Según su propia estimación, cada servicio le tomaba unos 10-15 minutos en el proceso end-to-end. Con 5 a 10 solicitudes diarias, y considerando que gran parte del día el operador está manejando, esta gestión se volvía un dolor de cabeza innecesario. Cuando un chofer terminaba un servicio y quería reportar algo (un peaje extra, un cambio de ruta), tenía que llamar o escribir, y el dueño lo anotaba a mano en su planilla.

## La solución

Tres agentes de IA, cada uno con una responsabilidad distinta:

- **Agente de creación:** lee cada correo entrante y decide qué hacer: agendar, derivar al agente de modificaciones, cancelar o pedir más información si falta algo.
- **Agente de modificación:** cuando un correo pide cambiar algo ya agendado, busca el evento correspondiente en el calendario (hasta 52 semanas hacia atrás, con un loop agéntico de búsqueda) y lo actualiza.
- **Agente de choferes:** cuando un servicio termina, el sistema le manda un WhatsApp automático al chofer pidiéndole que reporte novedades. Cuando el chofer responde (texto o audio, transcrito con Groq Whisper), este agente ya sabe a qué servicio corresponde y registra la novedad en la planilla.

El sistema vigila el correo en tiempo real con IMAP IDLE. Si un correo trae un PDF o Excel con varios servicios (un itinerario completo), Claude Vision lee el documento directamente y agenda cada servicio por separado, sin volver a llamar al agente de creación para cada línea. Un hilo en segundo plano revisa el calendario cada 5 minutos para detectar servicios recién terminados y disparar el aviso al chofer correspondiente.

Cuando un correo no trae suficiente información, el sistema le manda un WhatsApp al operador preguntando lo que falta. El operador responde, y el sistema retoma el correo original con esa información y lo agenda.

Las partes más difíciles fueron mantener el estado (archivos JSON) seguro entre tres hilos corriendo al mismo tiempo, evitar procesar el mismo correo dos veces sin perder ninguno si falla, y renderizar archivos Excel como imagen (con Pillow, celda por celda) porque no se puede mandar el binario directo a Claude.

## Stack técnico

- **Lenguaje:** Python
- **IA:** Anthropic Claude Sonnet 4 (los tres agentes, con tool use para el agente de modificación) + Claude Vision (lectura de PDF/Excel)
- **Integraciones:** Google Calendar API, Google Sheets API, Twilio WhatsApp, Groq Whisper (transcripción de audio)
- **Webhook:** Flask con waitress
- **Infraestructura:** DigitalOcean Droplet (Ubuntu), systemd, Cloudflare Tunnel, UFW

## Mi rol

Diseño y desarrollo completo del sistema con Claude Code como herramienta principal: arquitectura de agentes separados, definición de los esquemas de validación (Pydantic) para cada respuesta de la IA, manejo de errores y reintentos en cada punto de falla, y toda la configuración de despliegue (systemd, firewall, scripts de setup del servidor).

## Estado

En producción: los agentes de creación y modificación llevan meses operando sin intervención manual. La aprobación de Meta Business para WhatsApp Business API llegó a fines de septiembre de 2026, así que el agente de choferes ya está listo para su despliegue final, pendiente solo de la prueba de extremo a extremo. Última iteración: septiembre 2026.

---

*Código fuente privado por acuerdo con el cliente. Este documento describe el proyecto sin exponerlo.*
