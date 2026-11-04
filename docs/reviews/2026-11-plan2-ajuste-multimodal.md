# Revisión del ajuste multimodal del PLAN LFM3-2 — 2026-11-04

## Encargo y superficie

Encargo del Operador: integrar en el PLAN LFM3-2 existente las capacidades
soportadas por LFM3-Omni-2B (sin plan paralelo ni fases nuevas), priorizando
voz y conversación; después «corre ronda adversarial del ajuste al plan para
afinar y procede», «guarda todos los resultados para trazabilidad… graba los
test para aplicar en futuro hardware» y «el plan de pruebas debe ir antes del
commit». Autorizó commit, push y merge a main al cierre.

Autor: Claude Opus 5.5 (Claude Code), sesión del Operador. Hardware de las
sondas: MacBook Air M2, 16 GB. Motor y modelo congelados (ADR-001) sin cambio.
Evidencia: `evidence/plan2-ajuste-sesion/README.md` (P-1..P-14, C-1, C-2,
M-1, veredictos del Operador), `evidence/sondas-Mac14-2-2026-11-04/`,
`evidence/plan2-ajuste-gates.txt`.

## Ronda 1 — propuesta (subagente fresco, documental + 5 sondas)

Recibió sólo encargo, rutas y la propuesta; sin historial del autor.
Veredicto inicial fix-and-retry; relectura proceed condicionado a N1.

| ID | Sev. | Hallazgo | Disposición |
|---|---|---|---|
| H1 | HIGH | SSE y voz/video contradicen ADR-005 | ADR-006 propone la enmienda; índice la marca propuesta |
| H2 | HIGH | ffmpeg ya es dependencia oculta del motor; 8091 acepta audio/video sin límites | errata v1 = aviso PROHIBIDO; I1-V0 inventaria y fija PATH |
| H3 | HIGH | tools de voz no caben en MCP v1 | MCP v2 separado; v1 intacto |
| M1..M7 | MED | D-09 para voz real; CER previo; p95/N antes de medir; memoria medida; texto por archivo y 503; sólo input_audio primero; I2 excluye I1-V | aplicados en PLAN-2, iteraciones, ADR-007 |
| L1..L3 | LOW | sólo data URI; SSE en perfiles; AGENTS.md sin tocar | aplicados |
| N1 | MED | MCP v2 agrandaba I1-VA | sacado de VA a corte posterior |
| N2..N5 | LOW | ADR doble; -f sin verificar; cancelación hasta el motor; hash ffmpeg en readiness | ADR-006/007 separados; -f verificado (re-ASR exacto); gates VR/VV |

## Ronda 2 — diff aplicado (otro subagente fresco, lectura + gates)

Veredicto inicial fix-and-retry; relectura proceed con condición H-2 (este
reporte en el mismo commit); delta posterior (plan de pruebas y batería
portable) proceed.

| ID | Sev. | Hallazgo | Disposición |
|---|---|---|---|
| H-1 | HIGH | scripts de sesión escribían voz junto a sí, en ruta versionable | renombrados `*.py.txt`; `*_tu.wav` ignorado global |
| H-2 | HIGH | referencias a este reporte inexistente | este archivo |
| H-3 | HIGH | gate de tests con 1 fallo sin disposición | test_g3 intermitente (un `recv`), también en 310e7ff; lee hasta EOF; 15/15 y 77 OK |
| H-4/H-11 | MED/LOW | ejemplos pasaban salida del modelo por argv; sin consentimiento | `texto_seguro`, archivo 0600 + `-f`; exigen `LFM3_CONSENTIMIENTO_D09=si` |
| H-5..H-8 | MED | video contradictorio; orden no comprobado; ADR propuesto «enmendaba»; cuelgues | P-7/P-7b; orden por palabra; índice corregido; timeouts, EOF, 101, try por sonda |
| H-9, H-10, H-12 | LOW | voz say silenciosa; versión inútil; skip_dirs por nombre | fallo cerrado; línea `version:`; alcance declarado |
| N-1, N-2 | LOW | «colored» como red; texto vacío | `\b`; mensaje explícito |
| D-1..D-3 | LOW | hashes de fixtures sin comparar; `-hf` sin revisión; RSS Windows | JSON versionado y fallo cerrado; revisión y mmproj fijados; declarado no comparable |

Los revisores no ejecutaron la batería, los ejemplos ni la suite; esas
cifras son del autor y están en la evidencia. Revisión documental más
gates; no audita el prompt de sistema de los subagentes.

```text
id = plan2-ajuste-multimodal-2026-11-04
date = 2026-11-04
time_utc = 22:55:00Z
head_sha = 310e7ffec603991ddeb80ae9d70d817fc309375f
model = claude-opus-5-5
STATE = OK
GATE = 5/5 gates OK; unittest 77 OK (skipped=7); golden --rapido 11 pass 0 fail; git diff --check limpio; sondas_multimodal OK en M2
PENDING = D-08 y D-09 del Operador; ADR-006/007 propuestos; I1-V0..VV not_started; realtime bloqueado por ggml-org/llama.cpp#31689; skevi#84 abierto; hook pre-push con python3 del sistema
DECISION = proceed
OPERATIONS = commit en rama plan2-ajuste-multimodal, merge a main y push a origin (autorizados por el Operador en sesión)
AUTHORITY = encargo de integración multimodal y «corre ronda adversarial del ajuste al plan para afinar y procede» (Operador, 2026-11-04)
RISK = bajo: sólo documentos, una batería exploratoria, ejemplos con consentimiento y un test corregido; motor 8091 sin cambio; rollback por revert
EVIDENCE
- ronda 1 propuesta fix-and-retry con 3 HIGH corregidos y relectura proceed -> pass
- ronda 2 diff fix-and-retry con 3 HIGH corregidos, relectura y delta proceed -> pass
- cinco gates AGENTS al estado final (plan2-ajuste-gates.txt) -> pass
- unittest completo 77 OK tras corregir test_g3 intermitente -> pass
- golden del motor 11 pass 0 fail -> pass
- sondas_multimodal en M2 con fixtures verificados por hash -> pass
- voz llama-tts validada por oído del Operador; realtime con acento inglés -> pass
report_sha256 = 78cf2384ae62d7f12c7ebe86f11e22a048200f4fecb02f073659e27c6eb2486e
```
