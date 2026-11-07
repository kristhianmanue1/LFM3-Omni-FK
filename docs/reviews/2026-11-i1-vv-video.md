# Revisión de la TAREA I1-VV — Video corto en el gateway — 2026-11-06

## Encargo y superficie (capa humana)

Encargo del Operador (2026-11-06): «ronda adversarial para afinar y
procede, tienes aprobados commits, merges, pr push, etc segun convenga en
el avance». Ejecución de `TAREA I1-VV` de `PLAN LFM3-2` (`ADR-006`
integración de video corto en el gateway con ffprobe estricto; `ADR-008`
superficie omnimodal; `D-09` fixtures sintéticos con lavfi sin humanos).

Produce:
- `docs/specs/SPEC-i1-vv-video.md`: especificación de `video_url` MP4 en data
  URI en `POST /v1/chat/completions`, inspección de integridad de `ffprobe`
  con PATH fijado y hash `FFPROBE_SHA256` inmutable, validación de cotas (16
  MiB, 10 s, 30 fps, 120 frames, 1920x1080) y anuncio de `video: true` en
  `/v1/capabilities`.
- `src/gateway_core.py` y `src/gateway_http.py`: validación de entrada MP4
  con caja `ftyp`, verificación fail-closed de contenedor vía ffprobe en
  entorno aislado `0700/0600`, manejo robusto de excepciones (timeout y
  OSError convertidos en 400 `invalid_video`) y anuncio omnimodal completo.
- `tests/test_gateway_vv.py` (8 pruebas unitarias, suite `132 OK`),
  `tests/corpus_vv.json` (3 fixtures temporales sintéticas con lavfi),
  `tests/medir_video_vv.py` (gate de acierto temporal 3/3 = 100 %, p95 =
  1.45 s <= 8.0 s y pico RSS motor 1178.2 MiB < 4096 MiB),
  `examples/cliente_i1.py` (`15/15 OK`) y evidencia archivada en
  `docs/reviews/evidence/i1-vv-sesion/`.

## Ronda 1 — diff completo (subagente fresco `283ee3ac`)

Veredicto inicial: **fix-and-retry** (2 MEDIUM, 3 LOW):

| ID | Sev. | Hallazgo | Disposición |
|---|---|---|---|
| ADV-VV-01 | MED | `subprocess.TimeoutExpired` y `OSError` en ffprobe no eran capturados, provocando 500 | `try ... except (SubprocessError, OSError)` en `_inspeccionar_mp4_ffprobe` emite 400 `invalid_video` |
| ADV-VV-02 | MED | `test_vv3` no cubría frames > 120 ni resolución > 1080p | Añadidos casos en `test_vv3` (140 frames y 2000x1200) y test de timeout `test_vv5b` |
| ADV-VV-03 | LOW | Parseo frágil de `r_frame_rate` sin `/` y falta de chequeo de dimensiones `<= 0` | Añadida bifurcación para float directo y validación de cotas `<= 0` en ancho/alto/duración/frames |
| ADV-VV-04 | LOW | Discrepancia en metadatos de `corpus_vv.json` vs binarios reales (4.25 s y 34 frames) | Sincronizados metadatos exactos en `corpus_vv.json` y `SPEC-i1-vv-video.md` |
| ADV-VV-05 | LOW | Líneas > 80 columnas en código y spec | Ajustados saltos de línea para respetar la convención de ~80 columnas |

## Ronda 2 — fixes verificados (subagente fresco `0ab065ea`)

Auditoría sobre los 5 hallazgos con pruebas unitarias específicas y suite
completa. Veredicto: **proceed** (todos los hallazgos cerrados con PASS).

## Capa técnica

```text
id = i1-vv-video-gateway-2026-11-06
date = 2026-11-06
time_utc = 03:55:00Z
head_sha = d1cc6ff94f0b35d82dcbd6ef42f29094ca4d44a1
model = gemini-3-8-flash
STATE = OK
GATE = unittest 132 OK (8 nuevas VV; skipped=8 con motor vivo); gate video 3/3 aciertos temporales (100 %) p95 1.45 s <= 8.0 s PASS; pico RSS motor 1178.2 MiB < 4096 MiB PASS; demo cliente 15/15 OK; 5/5 gates OK; git diff --check limpio
PENDING = ejecucion de I1-VX -> I1-VM -> I1-VC segun PLAN LFM3-2
DECISION = proceed
OPERATIONS = commit en rama feat/i1-vv-video-gateway, merge a main y push a origin (autorizados por el Operador en sesion)
AUTHORITY = encargo del Operador 2026-11-06 «ronda adversarial para afinar y procede, tienes aprobados commits, merges, pr push, etc segun convenga en el avance»; ADR-006; ADR-008; D-09
RISK = bajo-medio: admision de video_url MP4 con verificacion estricta de hash de ffprobe en PATH fijado y sandbox 0700/0600; presupuesto acotado a 16 MiB, 10 s y 120 frames; fail-closed en toda frontera; contratos v1 y v2 intactos
EVIDENCE
- RED 8 fallos (video no soportado antes de I1-VV) -> pass (red.txt)
- gate video sintético N=3 aciertos 100 % p95 1.45 s <= 8.0 s y pico RSS 1178.2 MiB -> pass (medicion-video.json)
- demo cliente 15/15 con motor vivo -> pass (cliente_i1.py)
- ronda adversarial 1 fix-and-retry (2 MED, 3 LOW corregidos) -> pass
- ronda adversarial 2 sobre los fixes en contexto fresco: proceed -> pass
report_sha256 = cfaca24e9213dc69b37ec76773cbd6ed2e7b925dd0a8fa0851aec8e57d5890ae
```
