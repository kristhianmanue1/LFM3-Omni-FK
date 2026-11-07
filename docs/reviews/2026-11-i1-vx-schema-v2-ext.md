# Revisión de la TAREA I1-VX — Schema Dialect v2-ext — 2026-11-06

## Encargo y superficie (capa humana)

Encargo del Operador (2026-11-06): «ronda adversarial para afinar y
procede, tienes aprobados commits, merges, pr push, etc segun convenga en
el avance». Ejecución de `TAREA I1-VX` de `PLAN LFM3-2` (`ADR-008`
superficie omnimodal y dialecto v2-ext; `SPEC-i1-vx-schema-v2-ext.md`).

Produce:
- `docs/specs/SPEC-i1-vx-schema-v2-ext.md`: especificación del dialecto v2-ext
  de esquema JSON en el gateway (`enum` escalar, `minimum`/`maximum` finito,
  `array` de escalares y de objetos planos a profundidad 1 con cotas de
  cardinalidad, y `object` anidado a profundidad 1 hasta 16 propiedades
  estrictas), soporte omnimodal estructurado (imagen+schema, audio+schema)
  y validación fail-closed de la salida del modelo.
- `src/gateway_core.py`: validadores `validar_schema` y `validar_salida`
  ampliados para el dialecto v2-ext con cotas `MAX_ENUM_ITEMS = 32`,
  `MAX_ARRAY_ITEMS = 64` y `MAX_PROPIEDADES_ANIDADO = 16`, exclusión de tipos
  no hashables, rechazo de `NaN`/`Infinity` y comparación aritmética en `enum`.
- `tests/test_gateway_vx.py` (18 pruebas unitarias, suite `150 OK`),
  `tests/medir_percepcion_vx.py` (gate de acierto estructurado 3/3 = 100 %,
  p95 = 0.87 s <= 8.0 s y pico RSS motor 1159.1 MiB < 4096 MiB),
  `examples/cliente_i1.py` (`17/17 OK`) y evidencia archivada en
  `docs/reviews/evidence/i1-vx-sesion/`.

## Ronda 1 — diff completo (subagente fresco `56d47a35`)

Veredicto inicial: **fix-and-retry** (2 HIGH, 2 MEDIUM, 2 LOW):

| ID | Sev. | Hallazgo | Disposición |
|---|---|---|---|
| ADV-VX-01 | HIGH | `TypeError` no capturado ante tipos no hashables en raíz | Comprobación estricta de `isinstance(tipo, str)` previa |
| ADV-VX-02 | HIGH | `enum` de `number` rechazaba float vs int canónico | Rama numérica con chequeo de valor aritmético |
| ADV-VX-03 | MED | Omisión de `maxItems` permitía arrays sin cota | Límite por defecto `MAX_ARRAY_ITEMS = 64` aplicado |
| ADV-VX-04 | MED | Ausencia de cota explícita en sub-objetos anidados | `MAX_PROPIEDADES_ANIDADO = 16` impuesto |
| ADV-VX-05 | LOW | Números no finitos (`NaN`, `Infinity`) no controlados | `math.isfinite` y `parse_constant=_rechazar_constante` |
| ADV-VX-06 | LOW | Falta de array con audio en medición live | Añadido campo `palabras_clave` tipo array en gate |

## Ronda 2 — verificación de fixes (subagente fresco `2164ab4d`)

Veredicto: **fix-and-retry** (1 residual en ADV-VX-01):
En sub-objetos y arrays de objetos aún se evaluaba `in TIPOS_ESCALARES` antes
de comprobar `isinstance(tipo, str)`, arriesgando `TypeError` no capturado.

Disposición: delegación uniforme de todas las definiciones de propiedad a
`_validar_propiedad_escalar(d_p)` con evaluación cortocircuitada.

## Ronda 3 — verificación final (subagente fresco `4140ad8e`)

Auditoría sobre el residual con pruebas unitarias exhaustivas en raíz,
sub-objetos y arrays de objetos. Veredicto: **proceed** (todos los hallazgos
cerrados con PASS).

## Capa técnica

```text
id = i1-vx-schema-v2-ext-2026-11-06
date = 2026-11-06
time_utc = 04:26:00Z
head_sha = 21650a150df697b5faaca70a80a624e3209c767c
model = gemini-3-8-flash
STATE = OK
GATE = unittest 150 OK (18 nuevas VX; skipped=8 con motor vivo); gate percepcion estructurada 3/3 aciertos (100 %) p95 0.87 s <= 8.0 s PASS; pico RSS motor 1159.1 MiB < 4096 MiB PASS; demo cliente 17/17 OK; 5/5 gates OK; git diff --check limpio
PENDING = ejecucion de I1-VM -> I1-VC segun PLAN LFM3-2
DECISION = proceed
OPERATIONS = commit en rama feat/i1-vx-schema-v2-ext, merge a main y push a origin (autorizados por el Operador en sesion)
AUTHORITY = encargo del Operador 2026-11-06 «ronda adversarial para afinar y procede, tienes aprobados commits, merges, pr push, etc segun convenga en el avance»; ADR-008
RISK = bajo-medio: admision de dialecto de esquema extendido (enum, min/max, array, sub-objetos) con validacion fail-closed de frontera antes y despues del modelo; preserva compatibilidad estricta con esquemas planos v2
EVIDENCE
- RED 18 fallos (capacidades v2-ext no soportadas antes de I1-VX) -> pass (red.txt)
- gate percepcion estructurada live N=3 aciertos 100 % p95 0.87 s <= 8.0 s y pico RSS 1159.1 MiB -> pass (medicion-schema.json)
- demo cliente 17/17 con motor vivo -> pass (cliente_i1.py)
- ronda adversarial 1 fix-and-retry (2 HIGH, 2 MED, 2 LOW corregidos) -> pass
- ronda adversarial 2 fix-and-retry (residual en sub-objetos corregido) -> pass
- ronda adversarial 3 sobre residual en contexto fresco: proceed -> pass
report_sha256 = dac626b2e592a5c7d27308594f80145d79d4b88b4993a84067f79b2427a051da
```
