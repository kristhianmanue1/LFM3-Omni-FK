# PLAN LFM3-1 — Superficie de inferencia local: contratos, API y MCP

> Fase F0 cerrada en OK (docs/f0-analisis-y-requerimientos.md, FASE F0: OK,
> evidencia EV-1..EV-10). Este plan autoriza F1→F3 sobre esa base.
> Fuente de umbrales y capacidades medidas: docs/verificaciones-motor.md
> (batería B-T1..B-T9, 2026-11-02).

```text
PLAN LFM3-1 — Superficie de inferencia local: contratos, API y MCP
Autoriza: REQ-1..REQ-8 de docs/f0-analisis-y-requerimientos.md; SPEC y
CONTRATO que cada TAREA declara crear
Clase de tarea: Architectural — disparadores de 01 §2: proyecto nuevo,
plan nuevo, fronteras externas nuevas

Restricciones globales (verbatim del artefacto que autoriza):
- "LAN o público exigen nueva decisión registrada con api-key."
  — F0 CERRADA-6 (docs/f0-analisis-y-requerimientos.md §6)
- "La salida del modelo es dato no confiable — se valida en la frontera
  contra esquema cerrado antes de persistir o reenviar." — AGENTS.md
- "sus versiones se fijan en docs/f0-analisis-y-requerimientos.md y
  cualquier salto es una operación registrada, no una actualización
  silenciosa." — AGENTS.md (motor congelado por registro)
- "Ningún ofrecimiento a terceros fuera del ecosistema interno antes de
  verificar los términos de la licencia lfm1.0." — F0 REQ-8 (verificada,
  EV-10)

TAREAS:
TAREA F1-1
  Consumes: crea ADR-001 (decisión de motor congelado), base F0 EV-5/EV-6/EV-9
  Produce:  docs/adr/ADR-001-motor-congelado-registrado.md y docs/adr/00-INDICE.md
  Steps:
  - [ ] redactar ADR-001 con formato 02 §3.2 (Contexto: REQ-1/5/6; Decisión:
    llama.cpp 0.8.0 b11960 por Homebrew + GGUF Q4_K_M con mmproj, puerto
    8091, greedy, no-reasoning) — verificación: los cinco campos del formato
    presentes y Alternativas descartadas con dos opciones y razón
  - [ ] registrar índice de ADRs con entrada de ADR-001 — verificación:
    grep -c "ADR-001" sobre el índice devuelve 1 o más
  - [ ] correr gates locales — verificación: python3 scripts/check_sizes.py
    termina 0
TAREA F1-2
  Consumes: crea CONTRATO lfm3-omni/superficie-inferencia v1 (REQ-1, REQ-2,
    REQ-3, REQ-5, REQ-6, REQ-7, REQ-8) y CONTRATO lfm3-omni/mcp-tools v1
    (REQ-4) — disposición de la ronda adversarial F1 (hallazgo 2)
  Produce:  docs/contracts/superficie-inferencia-v1.md y
    docs/contracts/mcp-tools-v1.md
  Steps:
  - [ ] declarar Entrada/Salida/Errores/Invariantes/Compatibilidad por
    formato 02 §4.2: endpoints /health, /v1/models, /v1/chat/completions
    (texto, visión por image_url, tools, response_format json_schema),
    CORS y límites declarados (hallazgo 5), voz fuera de la frontera v1
    (hallazgo 6), errores 4xx estructurados — verificación: las
    cinco claves del formato presentes
  - [ ] invariantes del contrato tomados de B-T1..B-T9: greedy y
    determinismo 3/3 observado sin prometerlo entre reinicios, umbral
    mediana n=3 >= 15 tok/s, localhost único origen, fail-closed 400 —
    verificación: cada invariante cita su ID de caso B-T*
  - [ ] cláusula de licencia: consumo interno del ecosistema permitido;
    esquema de cobro a terceros sólo bajo umbral de licencia —
    verificación: la sección Invariantes cita REQ-8 y EV-10
TAREA F1-3
  Consumes: crea SPEC-1 (superficie, REQ-1/2/3/6/7) y SPEC-2 (MCP, REQ-4)
  Produce:  docs/specs/SPEC-1-superficie.md y docs/specs/SPEC-2-mcp.md
  Steps:
  - [ ] SPEC-1 con casos DADO/CUANDO/ENTONCES trazables uno a uno a
    B-T1..B-T9 — verificación: tabla de trazabilidad caso-REQ-test en la
    spec, sin casos sin REQ
  - [ ] SPEC-2 con comportamiento del servidor MCP: tools salud, infer
    texto y infer visión; errores con estado; presupuesto de contexto —
    verificación: formato 02 §2.2 completo con casos traducibles a test
  - [ ] ningún requisito fuera de F0 — verificación: cada SPEC declara
    "cubre:" sólo REQ-1..REQ-8
TAREA F1-4
  Consumes: SPEC-2
  Produce:  docs/adr/ADR-002-transporte-mcp-stdio.md
  Steps:
  - [ ] decidir transporte stdio para agentes CLI con alternativas
    descartadas: HTTP+SSE (requiere api-key y nueva decisión de red, v2) y
    el proxy MCP interno del propio llama-server (dirección inversa: el
    motor consume MCP, no lo expone) — verificación: Alternativas con dos
    opciones y razón de descarte cada una
  - [ ] actualizar índice de ADRs — verificación: grep -c "ADR-002" sobre
    docs/adr/00-INDICE.md devuelve 1 o más
TAREA F1-5
  Consumes: ADR-001, ADR-002, CONTRATO v1, SPEC-1, SPEC-2
  Produce:  docs/reviews/2026-11-f1-adversarial.md y reporte de fase F1
  Steps:
  - [ ] ronda adversarial con contexto fresco real sobre los cinco
    artefactos (disparadores de 04 §5.3 aplican: frontera externa nueva) —
    verificación: registro en docs/reviews con hallazgos y disposición
    (ADR-037: la propuesta remite, el registro cuenta)
  - [ ] gate de F1 por checklist de 02 §6 — verificación: los seis ítems
    marcados con evidencia en el reporte de fase; sin PARCIAL en contratos
TAREA F2-1
  Consumes: CONTRATO v1, SPEC-1, ADR-001, ADR-002
  Produce:  README.md, src/mcp_server.py (esqueleto), tests/golden/,
    examples/, run/
  Steps:
  - [ ] crear árbol y README (< 300 líneas, propósito, arranque, contrato) —
    verificación: wc -l README.md <= 300 y python3 scripts/check_sizes.py
    termina 0
  - [ ] esqueleto del servidor MCP sin lógica de negocio — verificación:
    python3 -m py_compile src/mcp_server.py termina 0
TAREA F2-2
  Consumes: docs/verificaciones-motor.md §3 (los casos vigentes, con
    procedencia; once tras la ronda adversarial F1)
  Produce:  tests/golden/casos.json y tests/run_golden.py (stdlib puro)
  Steps:
  - [ ] versionar los ocho casos con entrada, propiedad y procedencia;
    audio marcado known-fail con su registro — verificación: cada caso
    lleva las tres claves
  - [ ] runner que ejecuta contra localhost:8091 y reporta pass/fail/
    known-fail — verificación: python3 tests/run_golden.py imprime
    8 pass y 1 known-fail
TAREA F2-3
  Consumes: ADR-001 (runbook)
  Produce:  run/serve.sh y run/stop.sh
  Steps:
  - [ ] script de arranque con el runbook del F0 (puerto 8091, reasoning
    off, temp 0) y chequeo de salud post-arranque — verificación: bash
    run/serve.sh deja /health en 200 y termina 0
  - [ ] script de parada limpia — verificación: bash run/stop.sh termina el
    proceso y /health deja de responder
TAREA F3-1
  Consumes: SPEC-2, ADR-002
  Produce:  src/mcp_server.py funcional (handshake MCP y tools declaradas)
  Steps:
  - [ ] RED: test de handshake y de tool call que falla antes de implementar
    — verificación: salida del RED registrada en la evidencia de la tarea
  - [ ] GREEN: implementación mínima con validación en frontera de la
    salida del motor (response_format json_schema) — verificación: test en
    verde y python3 tests/run_golden.py sin regresión
  - [ ] integración real: registrar el servidor en el entorno de agentes y
    llamar una tool — verificación: transcripción de la sesión como
    evidencia
TAREA F3-2
  Consumes: CONTRATO v1
  Produce:  examples/cliente_minimo.py (stdlib, sin dependencias nuevas)
  Steps:
  - [ ] cliente que lista modelos, completa texto con esquema y completa
    con imagen — verificación: python3 examples/cliente_minimo.py imprime
    las tres salidas y termina 0
TAREA F3-3
  Consumes: B-T8 (fail conocido: audio en chat OAI no soportado)
  Produce:  verificación WS mínima de realtime o aplazamiento decidido
  Steps:
  - [ ] cliente WS mínimo de /v1/realtime con audio de say para ASR —
    verificación: transcripción contiene la palabra objetivo, o registro de
    aplazamiento con decisión del humano en docs/reviews
TAREA F3-4
  Consumes: todas las TAREAs previas
  Produce:  docs/reviews/2026-11-f3-adversarial.md, reporte dos capas y
    etiqueta v0.1.0 local
  Steps:
  - [ ] ronda adversarial final con contexto fresco sobre el sistema vivo —
    verificación: registro con hallazgos y disposición
  - [ ] reporte en dos capas (04 §9) y gates completos — verificación:
    python3 scripts/check_sizes.py, check_plans y check_reports terminan 0;
    activar clave reports del gate antes del reporte
  - [ ] etiqueta v0.1.0 local — verificación: git tag v0.1.0 ejecutado con
    autorización humana explícita registrada (operación fuera de lo
    ordinario; sin remoto declarado, no hay operación de red)

DoD: python3 scripts/check_sizes.py, scripts/check_plans.py y
scripts/check_reports.py terminan 0; check_templates de corpus y scripts
al día; python3 tests/run_golden.py en verde (8 pass, 1 known-fail
documentado); handshake MCP demostrado con evidencia; licencia citada en
el contrato; ronda adversarial F1 y F3 registradas en docs/reviews.
Partición: no aplica — el plan cabe bajo el límite de 300 líneas.
```

## Notas de operación

- Sin remoto declarado: ninguna TAREA incluye operaciones de red del
  repositorio; el servicio sí escucha (solo localhost, CERRADA-6).
- La etiqueta v0.1.0 exige autorización humana explícita por operación
  (AGENTS.md, reglas no negociables).
- Si la batería golden evoluciona en F3, cambia primero el contrato
  (Compatibilidad), después el caso: la regla de 06 §3 separa medición de
  cambio de componente.
