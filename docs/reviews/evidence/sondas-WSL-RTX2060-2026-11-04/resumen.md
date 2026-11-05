# Sondas multimodales — Linux-Intel-R-Core-TM-i7-10750H-CPU-2-60GHz (Intel(R) Core(TM) i7-10750H CPU @ 2.60GHz, 9 GB, GPU NVIDIA GeForce RTX 2060, 6144 MiB, 621.14) — 2026-11-05T01:29:03+00:00

Exploratorio, no gate (ver docstring de tests/sondas_multimodal.py).

- motor: b11960-8642541b2; modalities {'vision': True, 'video': True, 'audio': True}
- ASR input_audio: CER medio 0.0 sobre 10 frases; mediana 0.19 s
- B-T8 forma correcta (audio_url 400, input_audio 200): True
- /v1/audio/transcriptions: 200 en 0.19 s
- video temporal rojo→azul correcto: True ('The video starts with a solid **red** screen, and it ends with a solid **blue** screen.'; prompt_tokens=153)
- realtime mixto: CER de voz 0.027; primer audio 13.29 s (sin lang/voice en server-realtime (ggml-org/llama.cpp#31689))
- llama-tts es: CER re-ASR [0.0, 0.0, 0.0]; tiempos [7.58, 4.78, 3.71] s; RSS máx 1.37 GiB
