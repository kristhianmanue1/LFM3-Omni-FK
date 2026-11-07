# Revisión de la Fase I3 — Servidor MCP remoto desacoplado y catálogo omnimodal — 2026-11-07

## Encargo y superficie (capa humana)

Encargo del Operador (2026-11-07): «adelante tienes comits, puesh, merges autorizados
segun consideres en el abanse y despes aprobada la tarea», con directiva expresa de
aprovechamiento integral: «se aproveche todas las capacidades del modelo audio, video,
conversacion, reconocimiento de imagenes etc».

Superficie entregada (Fase I3 completa: TAREAS I3-D, I3-M e I3-U):
- `docs/adr/ADR-010-mcp-remoto-versiones-auth-transporte.md`: ADR formal de arquitectura
  MCP remoto sobre HTTPS/TLS (puerto 8443) con transporte Streamable HTTP (POST /mcp
  para JSON-RPC y GET /mcp para SSE), sesiones desacopladas por `Mcp-Session-Id`,
  matriz determinista de autorización por scopes y catálogo omnimodal integral.
- `docs/specs/SPEC-i3-mcp-remote.md`: especificación técnica normativa de las 8
  herramientas publicadas, esquemas de entrada/salida y protocolo de pruebas negativas.
- `src/mcp_remote.py`: módulo desacoplado del servidor MCP remoto:
  * `SessionRegistry`: control en memoria de sesiones aisladas por proyecto.
  * `MCPRemoteHandler`: enrutador de métodos (`initialize`, `ping`, `tools/list`,
    `tools/call`, `notifications/cancelled`).
  * Catálogo omnimodal completo: `health`, `capabilities`, `infer_text` (con schema
    v2-ext), `infer_vision` (PNG/JPEG en base64), `infer_audio` (WAV PCM 16kHz),
    `synthesize_speech` (llama-tts en español), `infer_video` (MP4 con inspección ffprobe)
    y `conversational_turn` (diálogo multi-turno interactivo).
  * Exclusión mutua de voz: respuesta inmediata `isError: true` (`tts_busy`) ante colisión.
  * Contención de egreso anti-SSRF: rechazo en frontera de esquemas URL externos.
- `src/gateway_http.py` y `src/gateway_core.py`: habilitación de rutas seguras `/mcp`
  preservando la allowlist cerrada de I1 y el despacho a través del dispatcher de cuotas.
- `examples/cliente_mcp_remoto_i3.py`: script de onboarding y demostración en Python
  stdlib (cero dependencias externas) ejercitando el ciclo de vida MCP completo.
- `tests/test_mcp_remote.py`: 12 pruebas unitarias y de integración exhaustivas
  cubriendo inicialización, catálogo, modalidades omnimodales, fallos de scope y
  aislamiento de sesiones.

## Ronda adversarial interna de verificación

1. **Aislamiento de sesiones y multi-inquilino**:
   - Hipótesis: ¿Puede un cliente con token de `proyecto-beta` acceder o reutilizar una
     sesión creada por `proyecto-alpha`?
   - Resultado: Verificado negativamente en `test_12_mcp_session_isolation`. Cualquier
     intento de presentar un `Mcp-Session-Id` perteneciente a otro proyecto devuelve
     `403 Forbidden` (`project_mismatch`) antes de procesar el método JSON-RPC.
2. **Contención estricta de egreso (anti-SSRF)**:
   - Hipótesis: ¿Puede un atacante inyectar URLs remotas (`http://...`, `file://...`)
     en los argumentos de imágenes, audio o video?
   - Resultado: Verificado en `test_06_mcp_tools_call_infer_vision_and_anti_ssrf`.
     La frontera exige validación estricta de cadenas base64 con cabeceras de firma mágica
     y rechaza de forma fail-closed cualquier esquema URI.
3. **Validación de salidas estructuradas**:
   - Hipótesis: ¿Se puede emitir una salida corrupta o no conforme si el modelo alucina?
   - Resultado: Verificado en `test_05`. La salida del modelo es tratada como dato no
     confiable y se valida contra el dialecto `schema v2-ext` antes de retornar el
     resultado; fallos devuelven `isError: true` (`salida_invalida`).
4. **Exclusión mutua de síntesis de voz**:
   - Hipótesis: ¿Colisionan dos llamadas concurrentes a `synthesize_speech`?
   - Resultado: Verificado en `test_08`. Al estar ocupado el cerrojo `LOCK_TTS`, la
     herramienta responde limpiamente `tts_busy` sin encolar ni agotar la memoria.

Veredicto adversarial: **proceed**.

## Capa técnica

```text
id = i3-mcp-remote-omnimodal-2026-11-07
date = 2026-11-07
time_utc = 17:50:00Z
head_sha = ccab09ee84e363bdbe52594e19a3bdd790c646cb
model = gemini-3-8-flash
STATE = OK
GATE = suite 275 OK (12 tests I3 nuevos); 5/5 skevi gates OK; check_sizes 1799/1800; check_plans OK; check_reports OK; check_templates OK
PENDING = cierre de Fase I3 y transicion a Fase I4 (perfiles W/D) segun PLAN LFM3-2
DECISION = proceed
OPERATIONS = commits y merge a main en rama feat/i3-d-mcp-remote-design autorizados por el Operador
AUTHORITY = autorizacion expresa del Operador 2026-11-07; PLAN-2; SPEC-i3-mcp-remote.md; ADR-010
RISK = bajo: motor loopback inalterado; endpoint MCP desacoplado bajo fair queuing y aislamiento estricto de scopes
EVIDENCE
- suite I3 12 pruebas de integracion mcp remoto -> pass
- suite completa 275 pruebas sin regresiones -> pass
- demo de onboarding cliente mcp remoto i3 -> pass
- aislamiento de sesiones entre proyectos -> pass
- contencion anti-ssrf en medios base64 -> pass
- exclusion mutua de tts con tts_busy -> pass
- validacion fail-closed de schema v2-ext -> pass
- cinco gates skevi pasando en verde -> pass
report_sha256 = 0691c7d7bfffd4c8e0dec3e7d6d3a879f285bcf4425a55f9f0962ed7a4443e06
```
