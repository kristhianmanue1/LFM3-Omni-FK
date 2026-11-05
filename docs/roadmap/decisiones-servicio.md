# Registro de decisiones de servicio — PLAN LFM3-2

Estado: vivo. Procedencia: `docs/roadmap/objetivo-y-alcance-servicio.md`
(§Decisiones pendientes) y regla del plan («Decisiones pendientes
bloquean su tarea»; «D-02..D-07 se deciden antes de sus gates»).

| ID | Decisión | Estado | Procedencia y fecha | Gate que la requiere |
|---|---|---|---|---|
| D-01 | Adoptar objetivo y contratos de PLAN-2 para ejecución | **ACEPTADA** | Operador, 2026-11-04, en conversación: «analiza y adelantes para primera iteracion» | I0-D (cumplido) |
| D-02 | Proyectos piloto, datos permitidos y responsable | pendiente | — | antes de I2 |
| D-03 | Host, dominio, TLS, red, identidad y presupuesto | pendiente | — | antes de I2 |
| D-04 | SLO, límites piloto y configuración de medición | pendiente | — | antes de benchmark I2 |
| D-05 | Repositorio/UI y autorización separada (frontExpert) | pendiente | — | antes de I4-UI |
| D-06a | Prioridad de modalidad | **ACEPTADA** | Operador, 2026-11-04, encargo de integración multimodal: «Primera prioridad: voz», luego conversación, visión/video y combinada | I1-V |
| D-06b | Hardware y presupuesto para candidatos (insumo: docs/roadmap/pruebas-hardware.md) | pendiente | — | antes de I6 |
| D-07 | Publicación comercial y oferta a terceros | pendiente | — | antes de ofrecerla |
| D-08 | Estrategia de voz (ADR-007: llama-tts; realtime fuera por #31689) | propuesta | ajuste PLAN LFM3-2, 2026-11-04 | antes de I1-VS |
| D-09 | Datos de audio e imagen reales | aceptada para las pruebas exploratorias de esta sesión, sin retención de medios | Operador, 2026-11-04: solicita y valida voz/cámara y conversación; archivos temporales eliminados | no promueve gates I1-V ni autoriza publicar medios personales |
| D-10 | Transcripciones para verificación futura | **ACEPTADA; implementación pendiente** | Operador, 2026-11-04: «en proximas se guardaran trascripciones para verificacion» | antes de la próxima prueba personal que se quiera auditar por contenido |

Responsable de D-02..D-10: el Operador. Sin fecha de calendario: la
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
