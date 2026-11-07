# Registro de decisiones de servicio — PLAN LFM3-2

Estado: vivo. Procedencia: `docs/roadmap/objetivo-y-alcance-servicio.md`
(§Decisiones pendientes) y regla del plan («Decisiones pendientes
bloquean su tarea»; «D-02..D-07 se deciden antes de sus gates»).

| ID | Decisión | Estado | Procedencia y fecha | Gate que la requiere |
|---|---|---|---|---|
| D-01 | Adoptar objetivo y contratos de PLAN-2 para ejecución | **ACEPTADA** | Operador, 2026-11-04, en conversación: «analiza y adelantes para primera iteracion» | I0-D (cumplido) |
| D-02 | Proyectos piloto, datos permitidos y responsable | formalizada (propuesta I2-D) | ADR-009, SPEC-i2 y dossier-operacion-i2 (2026-11-06) | antes de I2-P |
| D-03 | Host, dominio, TLS, red, identidad y presupuesto | formalizada (propuesta I2-D) | ADR-009, SPEC-i2 y dossier-operacion-i2 (2026-11-06) | antes de I2-P |
| D-04 | SLO, límites piloto y configuración de medición | formalizada (propuesta I2-D) | ADR-009, SPEC-i2 y dossier-operacion-i2 (2026-11-06) | antes de benchmark I2-P |
| D-05 | Repositorio/UI y autorización separada (frontExpert) | pendiente | — | antes de I4-UI |
| D-06a | Prioridad de modalidad | **ACEPTADA** | Operador, 2026-11-04, encargo de integración multimodal: «Primera prioridad: voz», luego conversación, visión/video y combinada | I1-V |
| D-06b | Hardware y presupuesto para candidatos (insumo: docs/roadmap/pruebas-hardware.md) | pendiente | — | antes de I6 |
| D-07 | Publicación comercial y oferta a terceros | pendiente | — | antes de ofrecerla |
| D-08 | Estrategia de voz (ADR-007: llama-tts; realtime fuera por #31689) | **aceptada** (Operador, 2026-11-05, sesión OpenCode: «Aceptar ADR-007») | ajuste PLAN LFM3-2, 2026-11-04; aceptación 2026-11-05 | cumplida: se aceptó antes de I1-VS |
| D-09 | Datos de audio e imagen reales | aceptada para las pruebas exploratorias de esta sesión, sin retención de medios (2026-11-04); **aceptada para los gates de I1-V con voz/cámara reales del Operador, condicionada a D-10 implementada** (Operador, 2026-11-05, sesión OpenCode: «Reales con D-10») | Operador, 2026-11-04 y 2026-11-05 | D-10 implementada antes del primer gate con reales; medios personales jamás publicados |
| D-10 | Transcripciones para verificación futura | **ACEPTADA e implementada (I1-VT)** | Operador, 2026-11-04 y 2026-11-05 (commit `c16ab5f`) | cumplida para voz local (`src/transcripciones.py`); pendiente cablear en SSE (`I1-VR`) |
| D-11 | Orientación local I1-V para agentes, robots y humanos (ADR-008: schema v2-ext, MCP local v2, CLI y perfil D en loopback antes de I2) | **ACEPTADA** | Operador, 2026-11-06: «ronda adversarial para afinar y procede, tienes aprobados commits, merges, pr push, etc segun convenga en el avance» | I1-VX / I1-VM / I1-VC |

Responsable de D-02..D-11: el Operador. Sin fecha de calendario: la
fecha límite es su gate (regla del plan); ninguna tarea pendiente de
estas decisiones se inicia antes. Mientras faltan, rigen los defaults
seguros de `objetivo-y-alcance-servicio.md` (sólo fixtures sintéticos,
sólo loopback, sin SLA, sin UI nueva, texto/imagen estables, sin oferta
comercial).

Registro de la aceptación D-01 (para trazabilidad): la propuesta
S-01..S-12 quedó publicada en el repo (commit `6cc7d78`) y el Operador
ordenó ejecutar la primera iteración sobre ella. El alcance aceptado es
el de I0: reparaciones locales compatibles con v1, adaptador local v2
sin activación remota, demo y rollback. No autoriza red, identidad
remota, UI, ni ninguna iteración posterior.

## Alcance de D-09/D-10 en el Dell G7 7700

Las pruebas personales se autorizaron y ejecutaron localmente; el Operador
confirmó voz en español, descripción visual, voz realtime en inglés y
continuidad de contexto. Esta sesión no guardó transcripciones ni medios
personales: no existe contenido que reconstruir o publicar retrospectivamente.

D-10 pide texto verificable en próximas sesiones. Implementar antes de
repetirlas: transcripción de entrada y respuesta asociadas por turno,
timestamps y parámetros/hashes, en archivos privados locales 0600 dentro
de `docs/reviews/evidence/privado/transcripciones/` (excluido de Git).
La retención será local para revisión del Operador; no hay borrado
automático acordado. Antes de publicar extractos, revisar y sanear el
contenido con el Operador. D-10 no autoriza conservar audio/video ni abrir
dispositivos sin un encargo de prueba. Procedencia: instrucción de cierre
del Operador; razón: auditar calidad/contexto sin confundir veredictos
humanos con transcripciones inexistentes.

## Formalización de D-02, D-03 y D-04 para Fase I2

La TAREA I2-D formalizó las especificaciones requeridas:
- **D-02**: Proyectos autorizados (`proyecto-alpha` para agentes/CLI analítico;
  `proyecto-beta` para robots/Perfil D o frontExpert), datos sintéticos o canarios
  sin PII, y aislamiento estricto de memorias y colas entre proyectos.
- **D-03**: Terminación TLS 1.3/1.2 en puerto 8443, gateway interno en
  127.0.0.1:8092, motor en 127.0.0.1:8091 exclusivo loopback; contención de
  egreso estricta (cero tráfico saliente durante inferencia); presupuesto de
  $0.00 USD en hardware propio con techo <= 10.0 GiB RSS global.
- **D-04**: SLO del piloto fijado antes de medir (éxito >= 99%, TTFT p95 <= 5s,
  total p95 <= 30s, cola p95 <= 10s) y arquitectura de dos experimentos
  separados (Experimento A: admisión end-to-end con carga 1/2/4/8; Experimento B:
  capacidad aislada del backend en ventana dedicada).
Detalles técnicos y operativos: `SPEC-i2-piloto-privado.md`, `ADR-009` y
`dossier-operacion-i2.md`.
