# Índice de ADRs

> Decisiones estructurales del proyecto. Inmutables: si la decisión
> cambia, se crea un ADR nuevo que sustituye al anterior (02 §3.2).

| ADR | Título | Estado | Fecha |
|---|---|---|---|
| [ADR-001](ADR-001-motor-congelado-registrado.md) | Motor congelado por registro (llama.cpp 0.8.0 b11960 + Q4_K_M) | aceptado, implementado (F0) | 2026-11-02 |
| [ADR-002](ADR-002-transporte-mcp-stdio.md) | Transporte del servidor MCP propio: stdio | aceptado; implementación F3-1 | 2026-11-02 |
| [ADR-003](ADR-003-publicacion-licencia-apache2.md) | Publicación del repo (LFM3-Omni-FK) y Apache-2.0 para el contenido; pesos siguen en LFM Open License v1.0; .an-kla/ sin versionar | aceptado (Operador, 2026-11-04) | 2026-11-04 |
| [ADR-004](ADR-004-estrategia-validacion-v2-stdlib.md) | Validación de frontera del adaptador v2: validador propio stdlib con dialecto cerrado | aceptado (I0-D, 2026-11-04); enmendado acotadamente por ADR-008 (I1-VX) | 2026-11-04 |
| [ADR-005](ADR-005-stack-http-gateway-loopback.md) | Gateway I1 sobre http.server stdlib; puerto 8092 configurable con fallo cerrado por colisión | aceptado (I1-D, 2026-11-04); enmendado por ADR-006 (capabilities y streaming) | 2026-11-04 |
| [ADR-006](ADR-006-modalidades-locales-y-streaming.md) | Modalidades locales del artefacto vigente por gate I1-V; SSE stdlib en loopback; ffmpeg como dependencia del motor | aceptado (Operador, 2026-11-04/06; ajuste PLAN LFM3-2) | 2026-11-04 |
| [ADR-007](ADR-007-estrategia-voz-local.md) | Voz local: ASR por 8091, TTS por llama-tts; /v1/realtime fuera (#31689) | aceptado (D-08, Operador 2026-11-05) | 2026-11-04 |
| [ADR-008](ADR-008-superficie-omnimodal-agentes-robots-cli.md) | Superficie omnimodal local para agentes, robots y humanos (schema v2-ext, MCP local v2, CLI y perfil D en I1-V) | aceptado (Operador, 2026-11-06) | 2026-11-06 |
| [ADR-009](ADR-009-identidad-red-egreso-piloto-i2.md) | Identidad, red, contención de egreso y supervisión para el piloto privado I2 | aceptado (I2-D, 2026-11-06) | 2026-11-06 |
| [ADR-010](ADR-010-mcp-remoto-versiones-auth-transporte.md) | Servidor MCP remoto desacoplado, transporte Streamable HTTP, autenticación por scopes y catálogo omnimodal integral | propuesto (I3-D, 2026-11-07) | 2026-11-07 |
