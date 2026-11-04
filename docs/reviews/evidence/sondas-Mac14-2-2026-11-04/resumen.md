# Sondas multimodales — Mac14,2 (Apple M2, 16 GB) — 2026-11-04T22:48:59+00:00

Exploratorio, no gate (ver docstring de tests/sondas_multimodal.py).

- motor: b11960-8642541b2; modalities {'vision': True, 'video': True, 'audio': True}
- ASR input_audio: CER medio 0.0 sobre 10 frases; mediana 0.34 s
- B-T8 forma correcta (audio_url 400, input_audio 200): True
- /v1/audio/transcriptions: 200 en 0.38 s
- video temporal rojo→azul correcto: True ('The video starts with a solid **red** screen, and it ends with a solid **blue** screen.'; prompt_tokens=153)
- realtime mixto: CER de voz 0.1892; primer audio 0.3 s (sin lang/voice en server-realtime (ggml-org/llama.cpp#31689))
- llama-tts es: CER re-ASR [0.0, 0.0, 0.0]; tiempos [2.97, 1.96, 2.21] s; RSS máx 2.93 GiB
