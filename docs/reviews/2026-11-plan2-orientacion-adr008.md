# Revisión de la orientación omnimodal (`ADR-008` y `PLAN LFM3-2`) — 2026-11-06

## Encargo y superficie (capa humana)

Encargo del Operador (2026-11-06): analizar crítica y propositivamente el
proyecto, el plan y sus ADRs para aprovechar las capacidades del modelo
para agentes, robots y humanos por CLI, API y MCP, y «ronda adversarial
para afinar y procede, tienes aprobados commits, merges, pr push, etc
segun convenga en el avance».

Archivos: `docs/adr/ADR-008-superficie-omnimodal-agentes-robots-cli.md`
(nuevo), `docs/adr/00-INDICE.md`,
`docs/adr/ADR-006-modalidades-locales-y-streaming.md`,
`docs/plans/PLAN-2-servicio-compartido.md`,
`docs/roadmap/iteraciones-servicio.md`,
`docs/roadmap/decisiones-servicio.md`, `.gitignore` y este reporte.

## Ronda 1 — propuesta (subagente fresco `0c388d1a`)

Veredicto inicial: **fix-and-retry** (2 HIGH, 3 MED, 1 LOW):

| ID | Sev. | Hallazgo | Disposición |
|---|---|---|---|
| H-1 | HIGH | `I1-VM` sobre `gateway_core` en memoria permitiría que subprocesos MCP lancen `llama-tts` en paralelo con `8092`, violando `ADR-007` (503 sin cola) y `REQ-5` | `ADR-008` §2, `PLAN-2` e `iteraciones` exigen que `I1-VM` valide con `gateway_core` y enrute toda ejecución por el gateway loopback `8092` (cerrojo único) |
| H-2 | HIGH | Ambigüedad de profundidad (`prof <= 2`), cierre de claves extra (`sobran`) en sub-objetos y exclusión de `bool` en `enum`/`minimum`/`maximum` | `ADR-008` §1 fija raíz = nivel 0 y sub-objeto = nivel 1, rechazo de claves sobrantes en todo objeto y exclusión explícita de `bool` numérico |
| M-1 | MED | Perfil D en `I1-VC` no exigía re-verificar `expires_at` post-inferencia, deduplicar `observation_id`, descartar salida incompleta ni acotar `device_id` local | `ADR-008` §3, `PLAN-2` e `iteraciones` exigen esos cuatro controles y dejan la identidad revocable remota en `I4` |
| M-2 | MED | Desalineación de `video` (`I1-VV`) entre `ADR-008` y `PLAN-2` | `I1-VM` e `I1-VC` consumen `I1-VV` y exponen `video` condicionado a que `I1-VV` cierre su gate (`capabilities.video: true`) |
| M-3 | MED | Índice de ADRs (`ADR-004`/`005`) y rango `D-02..D-10` desactualizados | Actualizados en `00-INDICE.md` y `decisiones-servicio.md` (`D-02..D-11`) |
| L-1 | LOW | 14 líneas de prosa > 80 columnas en `PLAN-2` y 1 en `ADR-006` | Envueltas a <= 80 columnas en todos los archivos |

## Ronda 2 — fixes verificados (subagente fresco `0c388d1a`)

Verificó los 6 hallazgos cerrados, los 5 gates de Skevi, `git diff --check`
y 0 líneas de prosa > 80 columnas. Veredicto: **proceed**.

## Capa técnica

```text
id = plan2-orientacion-adr008-2026-11-06
date = 2026-11-06
time_utc = 02:34:00Z
head_sha = f0c149d52725d35ec8e7387f87929ab2dbe844cd
model = gemini-4-argon
STATE = OK
GATE = 5/5 gates Skevi OK; 0 lineas de prosa > 80 col; ronda adversarial doble (fix-and-retry -> proceed); git diff --check limpio
PENDING = ejecucion de I1-VS -> I1-VR -> I1-VV -> I1-VX -> I1-VM -> I1-VC segun secuencia del plan
DECISION = proceed
OPERATIONS = commit en rama feat/plan2-orientacion-e-i1-vs, merge a main y push (autorizados por el Operador en sesion)
AUTHORITY = encargo del Operador 2026-11-06 «ronda adversarial para afinar y procede, tienes aprobados commits, merges, pr push, etc segun convenga en el avance»
RISK = bajo: solo ADRs, plan y hojas de ruta; sin cambios de codigo ni activacion remota; rollback por revert
EVIDENCE
- ronda 1 adversarial en contexto fresco (2 HIGH, 3 MED, 1 LOW corregidos) -> pass
- ronda 2 adversarial en contexto fresco sobre los fixes: proceed -> pass
- check_sizes.py, check_plans.py, check_reports.py y check_templates.py x2 -> pass
- verificacion de <= 80 columnas en prosa en todos los archivos modificados -> pass
report_sha256 = 2ba55048ca771123466cd89d5d71bafe5389618d3a483dc01a03d676c9007b23
```
