# Pruebas por hardware — LFM3-Omni

Estado: vivo. Procedencia: Operador, 2026-11-04 («graba los test para
aplicar en futuro hardware»; PC con Windows y Linux virtualizado, RTX de
6 GB). Razón: comparar velocidad, memoria y calidad del mismo artefacto
entre máquinas sin confundir plataforma con modelo. Relación con el plan:
insumo de D-06b (hardware, antes de I6) y de D-04 (SLO, antes de I2); no
es un gate ni promueve nada.

## Reglas

- Mismo artefacto que la línea base: llama.cpp build b11960 (0.8.0),
  `LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M` y su mmproj; hashes comparados
  contra `docs/reviews/evidence/sondas-Mac14-2-2026-11-04/resultados.json`.
  Otro binario del mismo build (Windows CUDA, Linux CUDA/Vulkan) es otra
  plataforma, no otro motor: se registra, no reemplaza la línea base M2
  ni cambia ADR-001. Un build distinto exige operación registrada.
- Solo loopback (127.0.0.1) en la máquina de prueba; sin api-key no se
  expone a LAN.
- Fixtures sintéticos versionados; voz o cámara reales sólo con D-09.
- Las cifras son observación; umbrales de gate se fijan en cada SPEC.

## Batería

`python3.12 tests/sondas_multimodal.py [--modelo GGUF] [--mmproj GGUF]`
con el motor arrancado en 127.0.0.1:8091. Registra hardware (CPU, RAM,
GPU vía `nvidia-smi` si existe), SO, versiones y hashes; mide:

| Sonda | Qué mide |
|---|---|
| ASR | CER y latencia sobre 10 fixtures `tests/golden/medios-binarios/asr_es_*.wav` (hashes en el JSON) |
| B-T8 | audio_url 400 / input_audio 200 |
| transcripción | /v1/audio/transcriptions |
| video | pregunta temporal rojo→azul (ffmpeg lavfi), en orden |
| realtime | voz mixta (documenta ggml-org/llama.cpp#31689) |
| TTS | llama-tts es: tiempo, CER de ida y vuelta y pico RSS donde se pueda medir |

Para velocidad de texto usar además `python3.12 tests/run_golden.py`
(B-T5: tok/s, mediana de 3).

## Máquina 2: Dell G7 7700, WSL2 Ubuntu y RTX 2060

Confirmación 2026-11-04: Windows CIM informa Dell Inc., G7 7700 y
16929980416 bytes de RAM física (16 GB nominales). Linux confirma
Intel Core i7-10750H @ 2.60 GHz; «7700» identifica el modelo Dell,
no la CPU. GPU: GeForce RTX 2060, 6144 MiB, driver Windows 621.14.
WSL2 dispone de ~9.7 GiB de RAM. Evidencia y resultados:
`../reviews/evidence/sondas-WSL-RTX2060-2026-11-04/`.
La ruta ejecutada fue WSL2/CUDA; Windows nativo no fue probado.

Rutas de ejecución, en este orden:

1. **Windows nativo, CUDA**: binarios oficiales de llama.cpp release
   b11960 (win cuda) + ffmpeg en PATH + Python 3.12.
   `llama-server -m <GGUF> --mmproj <mmproj-Q4_0> --reasoning off
   --temp 0 --host 127.0.0.1 --port 8091 -ngl 99`, con los archivos de la
   revisión HF `d508b88f08a5b4286f2d2805a6a8d69a0ff44c72`
   (`LFM3-Omni-2B-Q4_K_M.gguf` y `mmproj-LFM3-Omni-2B-Q4_0.gguf`). No usar
   `-hf` a secas: puede bajar otra revisión u otro mmproj. Comparar sus
   SHA-256 con la línea base ANTES de medir.
2. **WSL2 Ubuntu, CUDA**: WSL2 expone la GPU al Linux; compilar o usar
   binarios b11960 con CUDA. Mismo comando.
3. **VM clásica (Hyper-V/VirtualBox/VMware)**: sin acceso CUDA a la GPU
   por defecto; sirve sólo como referencia CPU (`-ngl 0`). No comparar
   con GPU.

Por ruta: correr la batería, `run_golden.py` y registrar
`nvidia-smi --query-gpu=name,memory.used --format=csv` con el modelo
cargado. Resultado en `docs/reviews/evidence/sondas-<máquina>-<fecha>/`.
Comparar con M2: tok/s (B-T5), latencia ASR, TTS por frase, primer audio
realtime, VRAM y RAM.

Portabilidad ya resuelta en la batería: fixtures versionados (no requiere
`say`), conversión con ffmpeg (no `afconvert`), rutas del artefacto con
`--modelo/--mmproj` o `LFM3_MODELO/LFM3_MMPROJ`, pico RSS de llama-tts con
`time -l` (macOS) o GNU `time -v` (Linux); en Windows queda «sin medir»,
así que la comparación de memoria de la PC sólo vale por la ruta WSL2.
Los fixtures se verifican contra `tests/golden/fixtures-audio-sha256.json`
y la batería falla cerrado si difieren.
Confirmado en WSL2: el paquete b11960 incluye llama-tts; el instalador
descarga revisión/hash explícitos a `run/build/wsl/cache/` y no usa `-hf`.
El driver 556.12 falló con PTX unsupported toolchain; 621.14 permitió
ejecutar las pruebas. Ver `../instalacion-wsl.md` y la retoma al final.
Antes de clonar en Windows: `git config core.autocrlf false` para que los
fixtures y los hashes no cambien.

## Registro

| Fecha | Máquina | Ruta | Evidencia | Nota |
|---|---|---|---|---|
| 2026-11-04 | MacBook Air M2 (Mac14,2), 16 GB, macOS 27.2 | Metal (Homebrew 0.8.0) | sondas-Mac14-2-2026-11-04/ | línea base |
| 2026-11-04 | Dell G7 7700, i7-10750H, RTX 2060 6 GB, 16 GB host / ~9.7 GiB WSL | WSL2 Ubuntu 24.04.5, CUDA 12.8 b11960 | sondas-WSL-RTX2060-2026-11-04/ | ASR/video/TTS y pruebas personales; observación exploratoria |

## Cierre y retoma del Dell

Informe: `../reviews/2026-11-dell-g7-7700.md`.
Guía reproducible y próximos pasos: `../retomar-dell-g7.md`.
Las pruebas personales no conservaron transcripciones ni medios; el
veredicto humano es evidencia de sesión, no un corpus auditable.
D-10 exige preparar transcripciones privadas antes de la próxima sesión.
