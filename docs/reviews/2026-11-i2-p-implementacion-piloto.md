# Revisión de la TAREA I2-P — Implementación del piloto privado HTTPS — 2026-11-06

## Encargo y superficie (capa humana)

Encargo del Operador (2026-11-06): «ok adelante» para la ejecución de
`TAREA I2-P` de `PLAN LFM3-2` (`SPEC-i2-piloto-privado.md`, `ADR-009`,
`dossier-operacion-i2.md`).

Produce:
- `src/gateway_auth.py`: módulo de autenticación con `TokenRegistry` (tokens en
  SHA-256 en `config/tokens.json` con permisos 0600 y recarga en caliente en
  memoria ante modificaciones/revocaciones), limitador de tasa `TokenBucket` por
  proyecto (429 `rate_limit_exceeded`), y despachador de colas con planificación
  justa `FairQueueDispatcher` (round-robin inter-inquilinos con discriminación
  de estado ante timeout, 503 `overloaded` y 504 `queue_timeout`).
- `src/gateway_tls.py`: terminador TLS en Python stdlib 3.12+ (`ssl.SSLContext`)
  en puerto 8443 con certificados locales (`basicConstraints = CA:TRUE`),
  control de presupuesto `Content-Length <= 32 MiB`, cabeceras
  `X-Service-Contract: 2`, `X-Request-Id` y sobre de error cerrado en fallos.
- `src/gateway_http.py`: integración de autenticación en frontera, comprobación
  previa de credenciales antes de ingesta de 32 MiB, resolución de scopes
  conjuntos por modalidad (`infer:text`, `infer:vision`, `infer:audio`,
  `profile:d`, `speech:synthesize`), cabeceras `X-Project-Id`, `X-Request-Id`
  y `X-Service-Contract: 2`, y liberación garantizada de slots.
- `src/gateway_core.py`: inclusión de `ftp://` en `validar_video_entrada`
  para completar la política estricta de no-egreso (anti-SSRF), y sobre de
  error `ErrorV2` con `type`, `param` y `retryable`.
- `run/stop.sh`: parada coordinada y segura de los listeners 8091, 8092 y 8443.
- `tests/test_gateway_i2.py`: 24 pruebas unitarias e integración en verde.

## Ronda 1 — auditoría adversarial (subagente fresco `6fffd6bb`)

Veredicto inicial: **fix-and-retry** (2 HIGH, 3 MEDIUM, 2 LOW):
- HIGH-1: Condición de carrera en expiración de cola en `acquire_slot` cuando
  otra petición del mismo proyecto está activa en el motor.
- HIGH-2: Bypass de validación de scope en peticiones multimodales
  (`profile:d` + imagen).
- MED-1: Ingesta de cuerpo de 32 MiB previa a la autenticación en `do_POST`.
- MED-2: Incompatibilidad de sobre de error y falta de cota en `gateway_tls.py`.
- MED-3: Certificados generados con `basicConstraints = CA:FALSE` fallan
  validación en clientes locales estrictos.
- LOW-1: Omisión de `ftp://` en `validar_video_entrada`.
- LOW-2: Cobertura de pruebas unitarias para escenarios de carrera y multimodales.

## Ronda 2 — verificación de fixes (subagente fresco `3659f9f0`)

Se implementó la discriminación con `estaba_en_cola` en el despachador de colas,
la acumulación de scopes requeridos (`_determinar_scopes_chat`), la validación
previa de cabeceras de identidad antes de leer 32 MiB, el acotamiento de
`Content-Length` y sobre cerrado en `gateway_tls.py`, la corrección de
`basicConstraints = CA:TRUE`, y la ampliación de la suite a 24 pruebas.
Veredicto final: **proceed**.

## Capa técnica

```text
id = i2-p-implementacion-piloto-2026-11-06
date = 2026-11-06
time_utc = 06:30:00Z
head_sha = 01dd284dfd676dc2dc230f76e30def0948e7b637
model = gemini-3-8-flash
STATE = OK
GATE = suite 232 OK (24 tests I2 nuevos); 5/5 skevi gates OK; check_sizes 1799/1800; check_plans OK; check_reports OK; check_templates OK; git diff --check limpio
PENDING = TAREA I2-V (vigilancia e inventario reproducible) segun PLAN LFM3-2
DECISION = proceed
OPERATIONS = commit en main y push a origin autorizados por el Operador
AUTHORITY = encargo del Operador «ok adelante» para TAREA I2-P; SPEC-i2; ADR-009
RISK = bajo: terminador TLS stdlib y auth Bearer multi-inquilino en loopback; sin dependencias externas; motor confinado a 8091
EVIDENCE
- suite I2 24 pruebas unitarias e integracion -> pass (test_gateway_i2.py)
- suite completa 232 pruebas sin regresiones -> pass
- verificacion de no-egreso anti-SSRF y fair queuing -> pass
- ronda adversarial 1 fix-and-retry (2 HIGH, 3 MED, 2 LOW corregidos) -> pass
- ronda adversarial 2 proceed en contexto fresco -> pass
report_sha256 = b768dca7e91fc744020a5c06bbcbd897860ec510d2991a56ee913e20950ba76f
```
