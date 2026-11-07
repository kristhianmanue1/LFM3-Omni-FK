# Revisión de la TAREA I1-VC — CLI unificado y Adaptador Perfil D — 2026-11-06

## Encargo y superficie (capa humana)

Encargo del Operador (2026-11-06): «ronda adversarial para afinar y
procede, tienes aprobados commits, merges, pr push, etc segun convenga en
el avance». Ejecución de `TAREA I1-VC` de `PLAN LFM3-2` (`ADR-008` §3;
`docs/contracts/perfiles-servicio-v2.md` §D; `SPEC-i1-vc-cli-perfil-d.md`).

Produce:
- `docs/specs/SPEC-i1-vc-cli-perfil-d.md`: especificación técnica del CLI
  unificado stdlib (subcomandos health, text, vision, audio, speech, video,
  pipes y `--json`) y del Adaptador de perfil D para robots y dispositivos con
  salvaguardas de tiempo real (deriva <= 2.0 s, descarte pre y post inferencia,
  deduplicación, secuencia, salida completa y enum cerrado).
- `src/cli.py`: CLI stdlib puro contra gateway 8092 con extracción de errores
  robusta y soporte de pipes stdin y binarios WAV.
- `src/adaptador_perfil_d.py`: adaptador local seguro de perfil D con
  verificación fail-closed de payloads, timestamps y descarte controlado.
- `tests/test_cli_vc.py` (8 pruebas unitarias) y
  `tests/test_adaptador_perfil_d.py` (10 pruebas unitarias con simulación
  temporal y anomalías de salida del modelo).
- `examples/simulador_robot_perfil_d.py`: simulador e2e ejecutable contra
  gateway vivo.

## Ronda 1 — diff completo (subagente fresco `24bda93c`)

Veredicto inicial: **fix-and-retry** (1 HIGH, 2 MEDIUM, 2 LOW):

| ID | Sev. | Hallazgo | Disposición |
|---|---|---|---|
| ADV-VC-01 | HIGH | `AttributeError` en `RobotAdapterD` ante salida no-dict del modelo | Validaciones `isinstance` estrictas en cuerpo, choice, message, propuesta y payload |
| ADV-VC-02 | MED | `AttributeError` en `cli.py` si cuerpo de error era string | `_extraer_mensaje_error` unificado para dict y str |
| ADV-VC-03 | MED | `JSONDecodeError` no capturado si 200 no era JSON válido | Captura limpia de decode error con exit 1 |
| ADV-VC-04 | LOW | Falta de tests específicos para subcomandos `audio` y `video` | Tests `audio` y `video` añadidos en `test_cli_vc.py` |
| ADV-VC-05 | LOW | Sin captura de `OSError` al escribir archivo en `speech` | Bloques `try...except OSError` con mensaje a stderr |

## Ronda 2 — verificación de fixes (subagente fresco `95cb65a3`)

Auditoría sobre los 5 hallazgos con suite completa (18 tests nuevos + 77 tests
MCP v1/v2). Veredicto: **proceed** (todos los hallazgos cerrados con PASS).

## Capa técnica

```text
id = i1-vc-cli-perfil-d-2026-11-06
date = 2026-11-06
time_utc = 04:58:00Z
head_sha = 4ec42fdb77bd6ab3c7ef9b3b771f719019a5c526
model = gemini-3-8-flash
STATE = OK
GATE = unittest 18 OK (CLI y Perfil D); suite MCP 77 OK; simulador robot perfil D e2e contra gateway vivo OK; 5/5 gates OK; git diff --check limpio
PENDING = cierre de fase I1 y transicion a I2 segun PLAN LFM3-2
DECISION = proceed
OPERATIONS = commit en rama feat/i1-vc-cli-robot-perfil-d, merge a main y push a origin (autorizados por el Operador en sesion)
AUTHORITY = encargo del Operador 2026-11-06 «ronda adversarial para afinar y procede, tienes aprobados commits, merges, pr push, etc segun convenga en el avance»; ADR-008; perfil D
RISK = bajo: CLI stdlib y adaptador analitico seguro para simuladores de robots; sin actuadores fisicos ni apertura de red externa; preserva invariantes fail-closed
EVIDENCE
- suite CLI y Perfil D 18 tests unitarios -> pass (test_cli_vc.py y test_adaptador_perfil_d.py)
- suite MCP total 77 tests intactos -> pass (test_mcp_server_v2.py y test_mcp_server.py)
- demo simulador robot perfil D e2e contra gateway vivo -> pass (simulador_robot_perfil_d.py)
- ronda adversarial 1 fix-and-retry (1 HIGH, 2 MED, 2 LOW corregidos) -> pass
- ronda adversarial 2 sobre los fixes en contexto fresco: proceed -> pass
report_sha256 = d651a2916a5def91b63dc569b71aaebcf75b7cee33156b4451cd02ab275e27e8
```
