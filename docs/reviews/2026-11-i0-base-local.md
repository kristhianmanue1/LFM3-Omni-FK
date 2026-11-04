# Ronda I0 — Base local reparada (PLAN LFM3-2)

Cierre de la TAREA I0-R/I0-U: adaptador local v2 en frontera, ciclo de
arranque reparado, B-T10 atribuible, inventario del artefacto y demo
local usable. SPEC: `docs/specs/SPEC-i0-adaptador-local-v2.md` (ADR-004
para la estrategia de validación; D-01 aceptada por el Operador,
2026-11-04, «analiza y adelantes para primera iteracion»).

Ronda adversarial con contexto fresco real (subagente independiente,
lectura de artefactos y diff, sondas propias): veredicto
**fix-and-retry** con 1 BLOCKER, 1 HIGH y 6 MED reproducibles, más 9
LOW. Disposición: BLOCKER y HIGH corregidos; MED corregidos (M-1..M-5)
o declarados como límite en el SPEC con su razón (M-6 → §2/§13);
LOW corregidos o documentados. La re-corrida completa detectó además
una regresión introducida por el propio fix H-1 (str vs bytes en el
proxy) que fue corregida antes del cierre. Sin HIGH/BLOCKER abiertos.

```text
id = i0-base-local-2026-11-04
date = 2026-11-04
time_utc = 19:30:00Z
head_sha = 59390abec458f1a6e10fe51f2ca973bf5fe4c6f9
model = zai-coding-plan/glm-5.3-flash
STATE = OK
GATE = 5/5 gates OK; golden --rapido 11 pass 0 fail; 34 tests OK (python3.12); demo adaptador 7/7 con motor real
PENDING = D-02..D-07 antes de sus gates; push sin autorizacion vigente; B-T5 omitido (--rapido); swap host sin atribucion per-pid (footprint exige root; reabrible en I2 con D-04)
DECISION = proceed
OPERATIONS = commit de TAREA en rama y merge ff a main, local; sin push ni tags
AUTHORITY = encargo del Operador 2026-11-04 (I0 local); ADR-004; SPEC I0; D-01 aceptada
RISK = bajo: alcance local (loopback 8091/8092); superficie v1 intocada; rollback probado con stop/serve
EVIDENCE
- RED de propiedades discriminantes antes de codigo (i0-red.txt, i0-red-ciclo.txt) -> pass
- suites unitarias y de ciclo en python3.12: 34 tests OK (i0-green-final.txt) -> pass
- golden del motor vivo 11 pass 0 fail con B-T10 atribuible (i0-golden.txt) -> pass
- demo I0-U texto/estructura/imagen/errores controlados 7/7 (i0-demo.txt) -> pass
- inventario motor+GGUF+mmproj por ruta/hash/licencia (i0-inventario.json) -> pass
- ronda adversarial fresca con veredicto fix-and-retry y disposiciones -> pass
- reg-corrida final detecto y corrigio regresion del fix H-1 -> pass
- cinco gates AGENTS en verde al estado final (i0-gates.txt) -> pass
- ciclo arranque: doble arranque, puerto ajeno, env adverso, readiness, stop seguro -> pass
- huella de estado: arbol limpio tras commit; MOTOR arriba al cierre -> pass
report_sha256 = d12d5195da5b0807aef4476773bfd06057924ba9e2b0836b96961ef3d6c67ff5
```

## Disposición de hallazgos de la ronda

| ID | Severidad | Hallazgo | Disposición |
|---|---|---|---|
| B-1 | BLOCKER | gate check_sizes en rojo (script sin entrada en manifiesto) | entrada añadida a `scripts/MANIFEST.json`; gates en verde |
| H-1 | HIGH | NaN/Infinity en salida validada pasaba como `valid` | `parse_constant` rechaza; salida → 502; entrada → 400; re-emisión canónica `allow_nan=false` |
| M-1 | MED | Content-Length no-ASCII → crash sin respuesta | validación ASCII+dígitos; 400 estructurado |
| M-2 | MED | `content: null` del backend → crash sin respuesta | TypeError/ValueError capturados → 502 `backend_error` |
| M-3 | MED | B-T10 con RSS vacío pasaba por 0 | salida vacía → fail; test propio |
| M-4 | MED | `stop.sh` matcheaba `--port 8091` dentro de `--port 80911` | frontera de palabra en el patrón |
| M-5 | MED | atajo idempotente declaraba arriba sin modelo | exige modelo efectivo; BLOQ si no; test r17b |
| M-6 | MED | `tools` sin validación de dialecto (re-emisión de JSON inválido) | integridad JSON garantizada; dialecto fino declarado límite I0 en SPEC §2/§13 (I1 lo cierra) |
| L-1..L-9 | LOW | varios | corregidos (basura tras IEND, claves extra en image_url, SOF restritos, docstring obsoleto, runtime 3.9→3.12+ en ADR/docstring) o documentados (dims declaradas, HTTP/1.0, skip de ciclo con motivo) |
