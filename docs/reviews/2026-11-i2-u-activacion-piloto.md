# Revisión de la TAREA I2-U — Activación del piloto HTTPS privado — 2026-11-07

## Encargo y superficie (capa humana)

Encargo del Operador (2026-11-06): «ok adelante» para la ejecución continua del
`PLAN LFM3-2`, abordando la `TAREA I2-U` según `ciclo-vida-modelo.md`, `ADR-009`
y `dossier-operacion-i2.md`.

Produce:
- `run/serve_pilot.sh`: script de orquestación del piloto HTTPS privado:
  - Cerrojo de concurrencia atómico (`run/serve_pilot.lock`) con detección y
    desalojo de procesos huérfanos/stale.
  - Comprobación fail-closed de puertos en escucha (8091, 8092, 8443) con aborto
    limpio (`cleanup_on_error`) ante ocupación ajena.
  - Verificación estricta de salud HTTPS usando el certificado CA raíz local
    (`--cacert "$CERT_PEM"`) eliminando cualquier bypass inseguro (`-k`).
  - Persistencia trazable de logs (`run/gateway.log`, `run/tls.log`) y PIDs
    activos (`run/gateway.pid`, `run/tls.pid`).
- `run/stop.sh`: ampliación del script de parada de emergencia con objetivo por
  defecto `--all` (8443, 8092, 8091), validación de identidad de proceso antes
  de señal (`es_proceso_servicio`) y remoción de cerrojos y pidfiles.
- `src/gateway_http.py`: endurecimiento de `_determinar_scopes_chat` con
  detección de subconjunto de propiedades obligatorias del Perfil D
  (`{"observation_id", "action"}`) y nombres de esquema (`action_proposal`,
  `robot_proposal`, `perfil_d`), interceptando evasiones de scope en la
  frontera del gateway HTTP con `403 Forbidden`.
- `examples/cliente_piloto_i2.py`: demostrador de onboarding en Python 3.12+
  stdlib (cero dependencias externas) con los 5 flujos canónicos:
  1. Consulta pública no autenticada de `/healthz` (200 OK).
  2. Inferencia de texto de `proyecto-alpha` (200 OK).
  3. Rechazo de propuesta robótica a `proyecto-alpha` sin `profile:d` (403).
  4. Inferencia estructurada Perfil D de `proyecto-beta` (200 OK).
  5. Rechazo de síntesis de voz a `proyecto-beta` sin `speech:synthesize` (403).
- `docs/reviews/evidence/i2-u-sesion/demo-cliente.txt`: transcripción íntegra de
  la ejecución de onboarding y aislamiento de permisos.
- `tests/test_piloto_live_i2.py`: 12 pruebas de integración exhaustivas
  cubriendo TLS handshake, Bearer auth, aislamiento de cuotas (burst 5),
  rechazo de tokens revocados, payload > 32 MiB, anti-SSRF, discrepancia de
  proyecto y parada limpia con rollback.

## Ronda 1 — auditoría adversarial (subagente fresco `d1ee9409`)

Veredicto inicial: **fix-and-retry** (5 hallazgos):
- SEC-01: Evasión del scope `profile:d` en `_determinar_scopes_chat` por cotejo
  superficial de `'proposal' in props`.
- OPS-01: `run/stop.sh` sólo detenía 8091 por omisión y la suite carecía de
  prueba de rollback real.
- OPS-02: Uso de flag insegura `-k` en `run/serve_pilot.sh`.
- OPS-03: Falta de cerrojo de concurrencia atómico, comprobación fail-closed de
  puertos en escucha y descarte de PIDs/logs.
- TST-01: Omisión de prueba negativa para Perfil D en Alpha y discrepancia en
  cuota de ráfaga (burst 3 vs 5).

## Ronda 2 — verificación de fixes (subagente fresco `81d136c3`)

Se aplicaron todas las correcciones: comprobación de propiedades mínimas y
nombres de esquema para Perfil D, parada limpia por defecto de todos los
componentes con prueba de rollback real en `test_11`, verificación TLS con
`--cacert` del CA local, cerrojo `mkdir` con trap, pidfiles y logs dedicados,
prueba negativa `test_04b` para Alpha y ráfaga de 5 peticiones en `test_06`.
Veredicto final: **proceed**.

## Capa técnica

```text
id = i2-u-activacion-piloto-2026-11-07
date = 2026-11-07
time_utc = 06:15:00Z
head_sha = 3a172d446ffdf4f5f1a13fe5e7ec5c117a5e5b86
model = gemini-3-8-flash
STATE = OK
GATE = suite 263 OK (12 tests I2-U nuevos); 5/5 skevi gates OK; check_sizes 1799/1800; check_plans OK; check_reports OK; check_templates OK; git diff --check limpio
PENDING = cierre de Fase I2 y transicion a Fase I3 (TAREA I3-D) segun PLAN LFM3-2
DECISION = proceed
OPERATIONS = commit en main y push a origin autorizados por el Operador
AUTHORITY = encargo del Operador «ok adelante» para TAREA I2-U; PLAN-2; dossier-operacion-i2.md
RISK = bajo: motor loopback permanece inalterado; autenticacion TLS y Bearer cierran frontera privada; rollback verificado
EVIDENCE
- suite I2-U 12 pruebas unitarias -> pass
- suite completa 263 pruebas sin regresiones -> pass
- demostracion de onboarding cliente piloto i2 -> pass
- verificacion de rollback y parada limpia -> pass
- ronda adversarial 1 fix-and-retry (5 hallazgos corregidos) -> pass
- ronda adversarial 2 proceed en contexto fresco -> pass
report_sha256 = 7f66e86125a7f526a5cf4af07e0fe8806ce710073c2ccce44acc2b5fed758e45
```
