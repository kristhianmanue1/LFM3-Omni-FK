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
| D-06 | Modalidad prioritaria, hardware y presupuesto | pendiente | — | antes de I6 |
| D-07 | Publicación comercial y oferta a terceros | pendiente | — | antes de ofrecerla |

Responsable de D-02..D-07: el Operador. Sin fecha de calendario: la
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
