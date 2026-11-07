# Revisión de la TAREA I2-V — Vigilancia e inventario reproducible — 2026-11-07

## Encargo y superficie (capa humana)

Encargo del Operador (2026-11-06): «ok adelante» para la ejecución continua del
`PLAN LFM3-2`, abordando la `TAREA I2-V` según `ciclo-vida-modelo.md`, `ADR-009` y
`dossier-operacion-i2.md`.

Produce:
- `src/vigilancia.py`: módulo de vigilancia reproducible y ciclo de vida:
  - Inspección de integridad estricta del baseline congelado (`llama-server`,
    `ffmpeg`, `ffprobe`, `llama-tts`, pesos GGUF y proyector `mmproj`)
    reproduciendo hashes SHA-256 y tamaños exactos en disco.
  - Verificación de presencia de responsables operativos, suplentes y canales de
    escalado en `docs/roadmap/dossier-operacion-i2.md`.
  - Control de presupuesto de red estricto (<= 12 peticiones, <= 5 MiB
    transferidos, <= 120.0 s de tiempo total por corrida).
  - Allowlist cerrada de fuentes oficiales con forzado fail-closed de HTTPS
    estricto y denegación de redirecciones fuera de dominio.
  - Máquina de estados de candidatos (`detected` -> `triaged` ->
    `evaluation_authorized` -> `evaluated` -> `rejected` | `promotion_proposed`
    -> `accepted` -> `canary` -> `active` -> `retired`) con anotación de
    bloqueo estructurada (`blocked`), trazabilidad de auditoría completa y
    capacidad de descarte definitivo directo durante el bloqueo.
  - Triaje temprano multidimensional: evaluación de licencias autorizadas (MIT,
    Apache 2.0, LFM Open License) con coincidencia flexible por regex,
    evaluación de compatibilidad técnica/hardware y evaluación de coste admisible.
  - Sanitización de metadatos no confiables en 5 capas: neutralización de secuencias
    ANSI completas, remoción de bytes de control, eliminación de etiquetas angulares
    XML/HTML, neutralización de directivas de inyección y colapso de longitud.
  - Ensayo reproducible de 9 escenarios reglamentarios de vigilancia.
- `tests/test_vigilancia.py`: 19 pruebas unitarias exhaustivas con 100% pass.
- `docs/reviews/evidence/i2-v-sesion/baseline-inventario.json`: captura íntegra
  del inventario del host anfitrión.
- `docs/reviews/evidence/i2-v-sesion/ensayo-vigilancia.json`: evidencia formal del
  ensayo de los 9 escenarios con resultado `todos_pasan: true`.

## Ronda 1 — auditoría adversarial (subagente fresco `15d532fa`)

Veredicto inicial: **fix-and-retry** (4 MEDIUM, 2 LOW, 1 gate limit):
- MED-1: `GestorPresupuestoRed` omitía presupuesto de tiempo (<= 120 s).
- MED-2: `CandidatoModelo` introducía `blocked` como pseudo-estado en historial y
  no preservaba trazabilidad de auditoría de bloqueos, ni permitía descarte directo.
- MED-3: `sanitizar_metadato` no neutralizaba secuencias ANSI completas ni etiquetas
  o directivas de inyección de prompt.
- MED-4: `triaje_temprano` omitía validación de compatibilidad de hardware y coste,
  con cotejo rígido de cadenas de licencia.
- LOW-1: `SafeRedirectHandler` permitía redirecciones a `http://`.
- LOW-2: Falta de pruebas unitarias para escenarios de límite de tiempo, bloqueo
  y descarte, y triaje de hardware/coste.
- GATE: Tamaño de `src/vigilancia.py` excedía el límite de 800 líneas.

## Ronda 2 — verificación de fixes (subagente fresco `5d30fb98`)

Se implementó el presupuesto temporal (`MAX_SEGUNDOS_CORRIDA = 120.0`), la
estructura formal de anotaciones de bloqueo con historial de auditoría y descarte
directo, el sanitizador en 5 capas contra inyecciones y ANSI, el triaje temprano
multicriterio, el forzado estricto a HTTPS en redirecciones, la ampliación de la
suite a 19 pruebas y la compactación del archivo a 773 líneas.
Veredicto final: **proceed**.

## Capa técnica

```text
id = i2-v-vigilancia-inventario-2026-11-07
date = 2026-11-07
time_utc = 00:50:00Z
head_sha = 5fe42582771526a3553eccd82872e1ed49f0509a
model = gemini-3-8-flash
STATE = OK
GATE = suite 251 OK (19 tests I2-V nuevos); 5/5 skevi gates OK; check_sizes 1799/1800; check_plans OK; check_reports OK; check_templates OK; git diff --check limpio
PENDING = TAREA I2-U (activacion piloto HTTPS privado) segun PLAN LFM3-2
DECISION = proceed
OPERATIONS = commit en main y push a origin autorizados por el Operador
AUTHORITY = encargo del Operador «ok adelante» para TAREA I2-V; PLAN-2; ciclo-vida-modelo.md
RISK = bajo: motor y pesos permanecen congelados; cero modificacion de runtime o dependencias; egreso acotado y presupuesto cerrado
EVIDENCE
- suite I2-V 19 pruebas unitarias -> pass
- suite completa 251 pruebas sin regresiones -> pass
- verificacion de integridad del baseline local -> pass
- ensayo de 9 escenarios de vigilancia reglamentarios -> pass
- ronda adversarial 1 fix-and-retry (7 hallazgos corregidos) -> pass
- ronda adversarial 2 proceed en contexto fresco -> pass
report_sha256 = cca2806687c5d0dd3421169d0c516f89014b47ed4bf7003645a66b9d224c3455
```
