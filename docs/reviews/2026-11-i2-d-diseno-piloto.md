# Revisión de la TAREA I2-D — Diseño del piloto privado HTTPS — 2026-11-06

## Encargo y superficie (capa humana)

Encargo del Operador (2026-11-06): «adelante» tras análisis crítico y propositivo
de la Fase I2. Ejecución de `TAREA I2-D` de `PLAN LFM3-2` (`ADR-009`;
`docs/specs/SPEC-i2-piloto-privado.md`; `docs/roadmap/dossier-operacion-i2.md`;
formalización de `D-02`, `D-03` y `D-04`).

Produce:
- `docs/specs/SPEC-i2-piloto-privado.md` (SPEC-PILOT): especificación técnica del
  piloto privado HTTPS, modelo de identidad Bearer con tokens en SHA-256 en
  `config/tokens.json` (0600), cabecera obligatoria `X-Project-ID`, matriz
  determinista de autorización por scope, terminador TLS stdlib en puerto 8443,
  allowlist estricta `data URI` (anti-SSRF), token bucket, prevención de inanición
  por planificación justa (*fair queuing*), y sobre de error cerrado con `retryable`.
- `docs/adr/ADR-009-identidad-red-egreso-piloto-i2.md`: decisiones estructurales de
  seguridad, topología de red, contención estricta de egreso y supervisión.
- `docs/roadmap/dossier-operacion-i2.md`: dossier operativo del piloto con
  responsables, proyectos (`proyecto-alpha` y `proyecto-beta`), cotas de memoria
  (<= 10 GiB global), SLOs fijados antes de medir y protocolo de contingencia.
- Formalización de decisiones `D-02`, `D-03` y `D-04` en `decisiones-servicio.md` y
  actualización de pasos en `PLAN-2-servicio-compartido.md`.

## Ronda 1 — auditoría adversarial (subagente fresco `352287cc`)

Veredicto inicial: **fix-and-retry** (3 HIGH, 3 MEDIUM, 2 LOW):
- H-01: Inconsistencia de timeouts y riesgo de starvation para Proyecto B (queue
  timeout 5s vs inferencia p95 30s de Proyecto A).
- H-02: Discrepancia normativa de error (queue_full a 429 en vez de 503 overloaded;
  falta de `retryable` y `request_id` en el sobre).
- H-03: Ambigüedad arquitectónica sobre el terminador TLS en puerto 8443.
- M-01: Falta de mapeo normativo de rutas/modalidades a scopes.
- M-02: Comportamiento no especificado ante `X-Project-ID` ausente o no alfanumérico.
- M-03: Omisión de `file://` en regla anti-SSRF y falta de regla fail-closed por
  inviabilidad de sandbox a nivel OS.
- L-01: Estado reportado en `registro-avance.md`.
- L-02: Desfase de alcance de `run/stop.sh` en dossier.

## Ronda 2 — verificación de fixes (subagente fresco `ca4950ed`)

Todos los hallazgos fueron subsanados: timeouts sincronizados a 10.0s con fair
queuing, 503 `overloaded` con sobre `retryable`, terminador TLS en Python stdlib
3.12+ documentado, tabla exhaustiva de scopes, validación de `X-Project-ID`,
allowlist positiva anti-SSRF con fail-closed, y estados sincronizados.
Veredicto final: **proceed**.

## Capa técnica

```text
id = i2-d-diseno-piloto-2026-11-06
date = 2026-11-06
time_utc = 06:05:00Z
head_sha = 5a6911097c20f48ca72100ee8cd2c54888f347ca
model = gemini-3-8-flash
STATE = OK
GATE = 5/5 skevi gates OK; check_sizes 1799/1800; check_plans OK; check_reports OK; check_templates OK; ronda adversarial R2 proceed
PENDING = implementacion de codigo en TAREA I2-P
DECISION = proceed
OPERATIONS = commit en main y push a origin autorizados por el Operador
AUTHORITY = encargo del Operador «adelante» tras analisis propositivo de I2
RISK = nulo: fase estrictamente documental y arquitectonica; no activa listeners remotos ni modifica configuracion en ejecucion
EVIDENCE
- SPEC-i2-piloto-privado con auth, scopes, red TLS, anti-SSRF, fair queuing y matriz de errores -> pass
- ADR-009 con arquitectura de seguridad, token registry, zero egress y supervision -> pass
- dossier-operacion-i2 con responsables, D-02, D-03, D-04 fijadas y SLOs antes de medir -> pass
- ronda adversarial 1 fix-and-retry (3 HIGH, 3 MED, 2 LOW corregidos) -> pass
- ronda adversarial 2 proceed en contexto fresco -> pass
report_sha256 = 3e52c6367e43509d2c7e802f4283f7e148e79c3bbfb32ee479099ca5543bf229
```
