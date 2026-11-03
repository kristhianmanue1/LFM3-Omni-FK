# Ronda adversarial F3 — registro en dos capas (2026-11-02)

> Registro conforme a ADR-016/ADR-022 y 04 §5.2. Cubre las DOS pasadas
> adversariales de F3 sobre el servidor MCP (contexto fresco real vía
> subagentes independientes, solo lectura) y sus disposiciones.
> La capa técnica autoritativa está en el bloque de abajo; la humana es
> proyección y no introduce afirmaciones ausentes en ella.

```text
id = f3-ronda-adversarial
date = 2026-11-02
time_utc = 01:33:45Z
head_sha = a66ac5bd7a3c06f2948276b2a328c31181fba59c
model = glm-5.3-flash (autodeclarado, nunca prueba)
session = ses_e6116d446ffeYIXYogNw2kkKuy; ses_e610600caffemXZSlmyjLs18Sq
STATE = OK
GATE = 04 parrafo 4 y 5.3 con DoD de PLAN LFM3-1; dos pasadas adversariales (r1: 15 hallazgos; r2: 13 hallazgos) con disposiciones aplicadas y re-verificadas por subagentes de contexto fresco
EVIDENCE
- unittest tests.test_mcp_server: 37 tests (handshake, validacion, clasificacion HTTP, tools con motor, motor caido) -> pass
- python3 tests/run_golden.py: 12 casos B-T1..B-T12 -> pass
- python3 examples/cliente_minimo.py: modelos, texto con esquema, vision -> pass
- sesion stdio real: initialize, tools/list, health, infer_text -> pass
- sonda WebSocket /v1/realtime: handshake HTTP 101 -> pass
- voz ASR completa por WebSocket -> inconclusive
- bash -n run/serve.sh y stop.sh, cerrojo con deteccion de huerfano y stop con propiedad de pid -> pass
- python3 scripts/check_sizes.py -> pass
- python3 scripts/check_plans.py -> pass
- python3 scripts/check_reports.py -> pass
- check_templates plantillas/scripts/corpus -> pass
- git status --short vacio y git diff --check limpio -> pass
- git tag v0.1.0 con autorizacion humana explicita registrada en sesion -> pass
DECISION = proceed
PENDING = voz realtime completa aplazada (protocolo sin documentar en build 0.8.0, handshake verificado); riesgo aceptado y registrado: sin techo de tamano para schema/image_base64 en localhost de consumidor unico
report_sha256 = 2c4307c19d78133438232d4552fb522e7130e0e5c428f01ea2aaf842d8d13219
```

## Capa humana — síntesis de las dos pasadas

### Ronda 1 (15 hallazgos: 1 BLOCKER, 2 HIGH, 7 MED, 5 LOW)

| # | Sev. | Hallazgo | Disposición aplicada |
|---|---|---|---|
| 1 | BLOCKER | "validación" de esquema falsa: solo parseaba JSON; validado:true mentía (REQ-7) | Validador real de subconjunto declarado (type/properties/required/items), fail-closed con claves no soportadas; test de regresión discriminante |
| 2 | HIGH | Crashes por payload del motor sin guardas (choices/message/content/usage) | _extraer_texto con forma cerrada; salida_invalida ante cualquier forma rara; usage no-objeto rechazado |
| 3 | HIGH | 4xx/5xx del motor reportados como "motor no disponible" (rama muerta) | HTTPError capturado aparte; 400 → "motor rechazó la entrada", 503 → "reintentable", resto genérico; cuerpo de error no-dict guardado |
| 4 | MED | usage/contenido/descripción sin validación de tipo | Tipos validados en frontera; omisión o violación → salida_invalida, sin fabricación |
| 5 | MED | Campos extra ignorados, schema:null aceptado, health con arguments | Superficie cerrada: campos no declarados rechazados nombrándolos; health sin campos; additionalProperties:false en tools/list |
| 6 | MED | imagen sin validación PNG/JPEG, MIME mentiroso | Firma de bytes en frontera (PNG/JPEG); MIME elegido por bytes; basura rechazada antes del motor |
| 7 | MED | Schema publicado contradecía al validador (rango de prompt en visión) | Contrato y validador alineados: prompt de visión 1..8000 declarado antes de congelar v1 |
| 8 | MED | Identificadores en español por el cable | Renombre completo a inglés (state/model/port/text/validated/description) en contrato, SPEC, código y tests, antes del primer consumidor |
| 9 | MED | Casos de error de SPEC-2 sin tests | Tabla de casos borde bajo test: 8001, max_tokens bool/0/4097, campo extra, schema null/no-soportado, salida no conforme, usage ausente |
| 10 | MED | stop.sh mataba pids sin verificar propiedad; carrera de dos serve.sh | Guard de propiedad con puerto específico; cerrojo mkdir con pid y detección de huérfano; kill -0 en la espera |
| 11 | LOW | Huecos de protocolo MCP (notificaciones, handshake, versión, -32602) | Notificaciones sin respuesta; initialize obligatorio (-32002); negociación de versión; tool desconocida → -32602 |
| 12 | LOW | Surrogate Unicode mataba el bucle principal | Escritura con backslashreplace + barrera final -32603; test E2E de main() |
| 13 | LOW | health reportaba el modelo desde constante | Contraste real contra /v1/models; divergencia → state "down" (principio 3) |
| 14 | LOW | Pre-check de serve.sh aceptaba cualquier /health | Verifica cuerpo {"status":"ok"} |
| 15 | LOW | Techo silencioso de visión | Declarado en el contrato (1024 tokens) |

### Ronda 2 (13 hallazgos: 4 HIGH, 5 MED, 4 LOW) sobre el código corregido

| # | Sev. | Hallazgo | Disposición |
|---|---|---|---|
| H1 | HIGH | Mensaje del cliente no-objeto (lista/string) o params escalar crasheaban | Guardas -32600 para mensaje y params no-objeto |
| H2 | HIGH | RecursionError sin capturar (JSON profundo, schema profundo) | Captura en json/schema + barrera final -32603 en el bucle |
| H3 | HIGH | Cuerpo de error HTTP con "error" no-objeto crasheaba _delegar | Guarda de tipos en el detalle del error |
| H4 | HIGH | El registro de la ronda 1 no existía en docs/reviews (proceso) | Este documento: registro único en dos capas que cubre ambas pasadas |
| M1 | MED | 200 con cuerpo no-JSON escapaba como excepción | Capturado → salida_invalida |
| M2 | MED | /health del motor con cuerpo no-objeto → AttributeError | Guarda isinstance en _motor_up |
| M3 | MED | Cerrojo huérfano de serve.sh bloqueaba para siempre | Pid dentro del cerrojo + detección de staleness |
| M4 | MED | stop.sh con grep de propiedad demasiado laxo | Grep específico "llama-server.*--port 8091" |
| M5 | MED | Clasificación HTTP y guard del bucle sin tests | Nueva clase ClasificacionHTTP (10 tests) + E2E de main() con surrogate |
| L1 | LOW | initialize sin id recibía respuesta | Notificaciones sin respuesta para cualquier método |
| L2 | LOW | Sin techo de tamaño para schema/image_base64 | Riesgo aceptado y registrado: localhost de consumidor único; a revisar en v2 si hay multi-consumidor |
| L3 | LOW | sleep 1 fijo en stop.sh podía dar BLOQ falso | Bucle de 3 reintentos |
| L4 | LOW | check_reports inactivo no vigilaba los registros | Clave reports activada en skevi-gate.json (este archivo pasa el gate; F1 exento por ser registro humano ADR-037 previo a la activación) |

### Pendientes de fase (no de ronda)

- **Etiqueta v0.1.0**: requiere autorización humana explícita por
  operación (AGENTS.md). Solicitada en sesión; sin ella, la fase queda
  PARTIAL por diseño.
- **Voz completa por /v1/realtime**: handshake verificado (HTTP 101);
  el protocolo de mensajes no está documentado en el build 0.8.0 →
  aplazamiento registrado. De integrarse, exigirá v2 del contrato.
