# SPEC I0 — Adaptador local v2 y ciclo de arranque reparado

Estado: activo (I0-D cerrado con ADR-004; sin PARCIAL). Procedencia:
PLAN LFM3-2 TAREA I0-R/I0-U; `docs/roadmap/iteraciones-servicio.md`
§I0; ADR-004; D-01 aceptada (2026-11-04). Este SPEC no modifica los
contratos v1 (`superficie-inferencia-v1`, `mcp-tools-v1`): v1 queda
preservado byte a byte en su comportamiento.

## 1. Frontera y superficie

- Adaptador: `src/adapter_v2.py`, HTTP stdlib (`http.server`), sólo
  loopback. Puerto por defecto 8092 (variable `LFM3_ADAPTER_PORT`,
  affordance de prueba documentada; el default es contractual hasta
  que I1 fije puerto).
- Backend: motor v1 en `LFM3_BACKEND` (default
  `http://127.0.0.1:8091`). El adaptador jamás reenvía nada que no
  pasó su frontera; el contador de llamadas al backend en las pruebas
  de política debe quedar en cero para todo rechazo.
- Rutas permitidas (allowlist cerrado): `POST /v1/chat/completions`,
  `GET /v1/models`, `GET /healthz`. Cualquier otra → 404 `not_found`.
  Sin streaming (`stream` presente → 400 `unsupported_field_value`).

## 2. Dialecto de petición (cerrado)

- Cuerpo ≤ 32 MiB (`Content-Length` verificada antes de leer).
- JSON estricto; claves top-level admitidas: `model`, `messages`,
  `tools`, `tool_choice`, `temperature`, `top_p`, `max_tokens`,
  `response_format`. Cualquier otra → 400 `unknown_field`.
- `messages`: lista no vacía; `role` ∈ {system, user, assistant};
  `content` string o lista de partes. Parte: `{type: "text", text}` o
  `{type: "image_url", image_url: {url}}`. Otro `type` → 400
  `unknown_content_type`.
- `image_url.url`: sólo `data:image/png;base64,…` o
  `data:image/jpeg;base64,…`. Decodificación estricta (base64 con
  validate). URL http(s) o cualquier otra → 400
  `external_url_rejected` **antes** del backend (la superficie v1
  hace fetch saliente; el adaptador la cierra para sus consumidores).
- `max_tokens`: entero 1..4096. `temperature`/`top_p`: número
  0..2 / 0..1. `model`: string.
- `tools`/`tool_choice`: passthrough estructural — se verifica
  integridad JSON (sin NaN/Infinity; re-emisión canónica con
  `allow_nan=false`) pero su dialecto fino es límite declarado de I0;
  I1 cierra el subdialecto.

## 3. Dialecto de imágenes (cerrado)

- PNG: firma 8 bytes, chunk IHDR presente con CRC válido, longitud
  IHDR 13, al menos un IDAT, IEND presente y **último byte del cuerpo**
  (basura tras IEND → rechazo); ancho*alto ≤ 16 777 216
  píxeles; decodificado ≤ 8 MiB.
- JPEG: SOI (FFD8FF), marcador SOF **sólo SOF0/SOF2** (otros SOF →
  rechazo) parseable con dimensiones,
  EOI (FFD9) al final; ancho*alto ≤ 16 777 216; decodificado ≤ 8 MiB.
- Fallo de cualquiera → 400 `invalid_image` (sin detalle del payload).

## 4. Dialecto de schema (cerrado; ADR-004)

- Sólo `response_format: {type: "json_schema", json_schema: {name,
  schema}}`, `name` string.
- `schema` admite exactamente: `type: "object"`, `properties` (mapa
  1..32), `required` (subconjunto de properties). Cada propiedad:
  `{"type": "string"|"integer"|"number"|"boolean"}`. Cualquier otra
  clave o tipo (object/array anidados, `$ref`, `additionalProperties`,
  `enum`, etc.) → 400 `unsupported_schema`.
- `additionalProperties: false` NO se soporta y NO se anuncia: si
  aparece, rechazo honesto `unsupported_schema` (nunca prometer
  enforcement que no existe).

## 5. Validación de salida del modelo

- Con `response_format` presente: contenido parseado como JSON; si no
  parsea → 502 `output_not_valid`, `detail: incomplete_output`, y el
  texto crudo viaja en `error.raw_content` (estado incompleto
  visible; estructura parcial jamás pasa como completa).
- Tipos: `true`/`false` NO satisfacen `number` ni `integer`; falta un
  `required` o sobra una propiedad no declarada → 502
  `output_not_valid`, `detail: schema_mismatch`.
- Sin `response_format`: passthrough íntegro del cuerpo del motor
  (compatibilidad v1) con cabecera `X-V2-Mode: passthrough`.

## 6. Errores (forma única)

`{"error": {"code", "message", "request_id"}}` + cabecera
`X-Request-Id`. Mensajes genéricos, sin paths ni eco del payload.
Códigos estables: `invalid_json`, `missing_messages`,
`unknown_field`, `unknown_content_type`, `external_url_rejected`,
`invalid_image`, `unsupported_schema`, `unsupported_field_value`,
`payload_too_large`, `not_found`, `backend_error`, `output_not_valid`.

## 7. Ciclo de arranque (run/)

- `serve.sh`: `--host 127.0.0.1` explícito; variables `LLAMA_ARG_*`
  del entorno eliminadas antes del exec (host adversario); cerrojo con
  dueño vivo identificado por el **comando del script** (ruta del
  directorio + `serve.sh`), no por grep de `llama-server`; huérfano
  (pid muerto o pid ajeno vivo) se recupera; pidfile se limpia en
  fallo; readiness verifica salud **y** modelo efectivo
  (`/v1/models` contiene el id esperado); presupuesto de espera
  configurable `LFM3_WAIT_BUDGET` (default 240 intentos, sin cambio
  contractual).
- `stop.sh`: mata sólo (a) el pid del pidfile cuya línea de comando
  sigue siendo `llama-server … --port 8091`, y (b) el pid **listener**
  de `lsof` con la misma verificación de propiedad. Sin `pkill`
  amplio: un proceso ajeno cuyo comando mencione el patrón (o un pid
  reciclado) sobrevive. Puerto ocupado por ajeno tras intento → BLOQ
  explícito.

## 8. Recursos (B-T10)

- El pid se deriva del **listener** (`lsof`), con verificación de
  propiedad por basename del binario; sin pid único no hay pass.
- Gate atribuible: RSS del pid < 4 GiB (REQ-5).
- Swap (`sysctl vm.swapusage`): global del host, **se reporta sin
  atribuir ni usar como umbral** — la atribución per-pid exige root
  (`footprint`: "Must run as root", evidencia en
  `docs/reviews/evidence/`). Enmienda 2026-11-04: el umbral swap
  global de la versión inicial del SPEC atribuía al motor swap ajeno;
  queda declarado como limitación y puede reabrirse en I2 con
  tooling privilegiado y decisión D-04.
- Se reporta además el piso mmapeado (binario + GGUF + mmproj).

## 9. Inventario del artefacto (I0-R)

`tools/inventario_motor.py`: ruta, revisión (`llama-server
--version`), sha256, bytes y licencia declarada de binario, GGUF y
mmproj. JSON a stdout; falla cerrado si falta un artefacto.

## 10. Matriz REQ-SPEC-test

| REQ | Propiedad | Verificación |
|---|---|---|
| R1 | campo top-level desconocido → 400 sin llamar al backend | `test_adapter_v2::r1` |
| R2 | schema anidado → 400 sin llamar al backend | `test_adapter_v2::r2` |
| R3 | `type` no-string / bool como number → rechazo u `output_not_valid` | `test_adapter_v2::r3` |
| R4 | `additionalProperties` → 400 honesto | `test_adapter_v2::r4` |
| R5 | URL de imagen externa → 400, contador 0 | `test_adapter_v2::r5` |
| R6 | PNG/JPEG truncados → 400, contador 0 | `test_adapter_v2::r6` |
| R7 | firma falsa (CRC/SOI) → 400, contador 0 | `test_adapter_v2::r7` |
| R8 | exceso de píxeles → 400, contador 0 | `test_adapter_v2::r8` |
| R9 | JSON malformado / sin messages → 400 | `test_adapter_v2::r9` |
| R10 | salida parcial → 502 `output_not_valid` | `test_adapter_v2::r10` |
| R10b | contenido ilegible del backend → 502 `backend_error` | `test_adapter_v2::r10b` |
| R11 | passthrough válido → 200 y cuerpo íntegro | `test_adapter_v2::r11` |
| R12 | salida estructurada válida → 200 | `test_adapter_v2::r12` |
| R13 | doble arranque: segundo BLOQ, un solo motor | `test_ciclo_arranque::r13` |
| R14 | cerrojo: dueño vivo, huérfano, pid reciclado | `test_ciclo_arranque::r14` |
| R15 | puerto ocupado por ajeno → BLOQ limpio | `test_ciclo_arranque::r15` |
| R16 | `LLAMA_ARG_*` neutralizados + host explícito | `test_ciclo_arranque::r16` |
| R17 | readiness exige modelo efectivo | `test_ciclo_arranque::r17` |
| R17b | atajo idempotente exige modelo efectivo (BLOQ si no) | `test_ciclo_arranque::r17b` |
| R18 | `stop.sh` no mata ajenos (ni por subcadena de puerto) | `test_ciclo_arranque::r18` |
| R19 | B-T10 sin PID o RSS vacío falla; pid por listener con propiedad | `test_recursos_bt10` |
| R20 | inventario por ruta/hash/licencia | corrida `tools/inventario_motor.py` |
| R21 | NaN/Infinity: entrada → 400; salida validada → 502 | `test_adapter_v2::r3c/r21` |
| R22 | basura tras IEND y claves extra en `image_url` → rechazo | `test_adapter_v2::r6c/r5b` |

## 11. Comandos exactos

Runtime: **python 3.12+** (decisión del Operador, 2026-11-04; en esta
máquina, `python3.12`). Los comandos fijan el intérprete explícito.

```bash
# Política (sin motor): unidades de adaptador, ciclo de arranque y B-T10
python3.12 -m unittest tests.test_adapter_v2 tests.test_ciclo_arranque \
  tests.test_recursos_bt10 -v

# Motor vivo: batería contractual y suite v1 existente
bash run/serve.sh
python3.12 tests/run_golden.py --rapido
python3.12 -m unittest tests.test_mcp_server -v
python3.12 tools/inventario_motor.py
bash run/stop.sh
```

## 12. Rollback y compatibilidad

- Adaptador: detener proceso (Ctrl-C / kill del pid propio); nada
  persiste. v1 no se tocó en su superficie ni contrato; `serve.sh` y
  `stop.sh` conservan defaults (8091, localhost, greedy).
- Reversión completa: revert del commit de la TAREA I0 en la rama;
  el golden set previo (12 casos) sigue siendo la regresión
  contractual.

## 13. Riesgos y límites declarados

- Sin streaming/SSE (I0); concurrencia por hilos stdlib sin cuotas
  (I2 añade identidad/admisión); sin auth (sólo loopback); dialecto
  schema intencionalmente subset (ADR-004).
- Dimensiones de imagen según cabeceras declaradas (sin decodificar
  la imagen completa; SOF restritos a SOF0/SOF2): un SOF mentiroso
  declara píxeles falsos, no abre paso a datos.
- HTTP/1.0 por petición (sin keep-alive): una Content-Length por
  conexión; I1 revisará al activar HTTP/1.1.
- El swap reportado por B-T10 es global del host (§8, enmienda):
  atribución per-pid exige root; I2 puede reabrir con tooling
  privilegiado bajo D-04.
- `tools`/`tool_choice`: integridad JSON verificada; dialecto fino
  pendiente para I1 (§2).
- El adaptador es la semilla de I1, no el gateway definitivo; su
  puerto y knobs son affordances documentadas, no contrato.
