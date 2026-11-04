# Evidencia de sesión — ajuste multimodal del PLAN LFM3-2 (2026-11-04)

Hardware: MacBook Air M2 (Mac14,2), 8 núcleos, 16 GB RAM, macOS 27.2.
Motor: llama-server 0.8.0 b11960-8642541b2 en 127.0.0.1:8091 con
`--reasoning off --temp 0`; modelo Q4_K_M, mmproj Q4_0 (ADR-001).
Todo loopback. Las cifras son observación exploratoria, no línea base.
Medición reproducible por hardware: `tests/sondas_multimodal.py`; corrida
M2 en `../sondas-Mac14-2-2026-11-04/` (resultados.json, resumen.md;
WAV/MP4 en medios-binarios/).

## Sondas (transcritas de la salida de la sesión)

| ID | Sonda | Resultado |
|---|---|---|
| P-1 | GET /props | modalities vision/video/audio = true |
| P-2 | chat input_audio, WAV `say` 16 kHz | ASR español exacto, 1.76 s (luego 0.36 s mediana, 10 frases, CER 0) |
| P-3 | audio + pregunta de comprensión | devolvió transcripción, no respuesta |
| P-4 | chat audio_url (forma de B-T8) | 400 unsupported content[].type |
| P-5 | /v1/audio/transcriptions multipart | exacto, 0.57 s |
| P-6 | chat modalities ["text","audio"] | ignorado: sólo texto |
| P-7 | video 2.5 s rojo→azul, prompt propio | respuesta temporal falsa (68 tokens) |
| P-7b | video 4 s a 8 fps, prompt de la ficha (sondas_multimodal) | correcta y en orden: red → blue (prompt_tokens=153) |
| P-8 | /v1/realtime solo audio, temp 0 / 0.8 / 0.4+rp1.2 | ininteligible; un caso 215 s de bucle |
| P-9 | llama-tts --tts-lang es | clara; re-ASR exacto |
| P-10 | /v1/realtime texto+audio | texto correcto; voz con acento inglés |
| P-11 | código server-realtime.cpp b11960 y master v0.9.0 | sin lang/voice al gen-audio; tts.cpp sí |
| P-12 | conversación por turnos de 6 s (conversa.py) | 5 turnos; ASR 0.4–0.9 s; voz 2.6–11 s; un turno cortado |
| P-13 | conversación casi tiempo real (conversa_rt.py) | 6 turnos; primera voz 2.8–4.4 s tras silencio |
| P-14 | issues | kristhianmanue1/skevi#84; ggml-org/llama.cpp#31689 |
| C-1 | foto cámara FaceTime → visión → llama-tts | descripción correcta (Operador); 66 s incluye permiso de cámara |
| C-2 | segunda foto | descripción 1.4 s (276 tokens); voz +12.6 s; correcta (Operador) |
| M-1 | pico RSS llama-tts (/usr/bin/time -l) | 2.95 GiB por proceso |

## Veredictos del Operador (oído y vista humanos)

- llama-tts: «clara, un poco semi robotizada pero bien, buena
  pronunciación en español».
- realtime texto+audio: «la voz se oye en español pero con acento de
  voz en inglés».
- cámara: «muy bien lo describió muy bien».

## Archivos

- `medios-binarios/`: muestras sintéticas (llama-tts correcto; realtime
  solo audio, mixto, y los primeros 10 s del bucle de 215 s).
- Scripts de sesión como texto, NO ejecutables (`*.py.txt`): `ws_probe`,
  `rt2`, `rt5`, `conversa`, `conversa_rt`, tal cual corrieron desde el
  scratchpad. Escriben audio junto a sí mismos: no se ejecutan desde aquí.
  La versión reutilizable segura es `examples/conversacion_voz_local.py`.
- `propuesta-ajuste-plan2.md`: propuesta con §6 de correcciones R1.
- Borradores de issues enviados: `issue-skevi-python312.md`,
  `issue-llamacpp-realtime-lang.md`.
- Voz e imagen del Operador: `../privado/sesion-2026-11-04/`, excluido de
  git (repo público; D-09 pendiente). Las fotos se borraron tras describir.
