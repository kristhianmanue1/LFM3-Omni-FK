# Instalación y diagnóstico en esta PC

Ruta: raíz del checkout local.
Plan previo: [pruebas por hardware](roadmap/pruebas-hardware.md).
Especificación: [instalador WSL](specs/SPEC-wsl-install.md).

El código se recuperó de main@9c0035b mediante el conector GitHub y se
verificaron los 154 blobs originales. Al cerrar, se restauraron metadatos
Git desde un clon público sin checkout, conservando el trabajo local.
Los cambios actuales y su publicación se describen en
`reviews/2026-11-dell-g7-7700.md`; el informe inicial es histórico.

## Estado inicial y verificación posterior

Ubuntu 24.04.5 en WSL2 x86_64, Python 3.12.3, unos 9.7 GiB de RAM y
12 GiB de swap visibles. ffmpeg, ffprobe y lsof están disponibles.
Al iniciar el encargo no había llama-server, llama-tts ni pesos GGUF.
AN-KLA y su memoria local no estaban presentes; no se inicializaron.

La sesión inicial bloqueaba sockets (`socket.socket()` producía EPERM), no resolvía
GitHub/Hugging Face y no exponía `/dev/dxg`. `nvidia-smi` informaba «GPU
access blocked by the operating system». Esto describe la sesión de
ejecución; no demuestra una avería del driver de Windows ni identifica el
modelo de la GPU. No se cambió la configuración del host.

El primer intento de instalación falló por DNS, sin publicar un runtime
incompleto. Posteriormente el Operador instaló los artefactos desde WSL.
El driver Windows 556.12 falló con PTX unsupported toolchain; tras su
actualización a 621.14 y habilitar acceso del ejecutor, se comprobó el
motor vivo en CUDA sobre la RTX 2060: salud, modelo efectivo e inferencia
correctos; golden 12/12 y suite de 83 pruebas sin fallos, con 7 omitidas
porque 8091 ya estaba ocupado por el motor. Evidencia posterior:
`reviews/evidence/instalacion-wsl-2026-11-04/runtime-live.json`,
`golden-live.txt` y `unit-live.txt` en ese mismo directorio.
La VRAM observada fue 3993 MiB de 6144 MiB. El throughput observado fue
117 tok/s de mediana; la suite se ejecutó concurrentemente, por lo que
esta cifra no constituye una línea base de rendimiento aislada.

## Completar desde una terminal WSL con red y GPU

Desde la raíz del proyecto:

```bash
python3 scripts/install_wsl.py --check
python3 scripts/install_wsl.py
python3 scripts/install_wsl.py --serve
```

El primer comando diagnostica DNS, sockets, GPU y dependencias. El segundo
descarga y verifica los dos paquetes oficiales CUDA 12.8 de b11960, los
pesos Q4_K_M y el proyector Q4_0 de la revisión HF exacta del plan.
Los hashes están en `run/wsl-artifacts.json`; las descargas y extracción
quedan en `run/build/wsl/`, excluido de Git. No se necesita sudo, pip ni
Homebrew. La combinación efectiva se verificó con el driver 621.14.

El tercer comando contrasta el inventario de archivos, hashes de pesos,
versión del motor y detección de CUDA0; arranca en primer plano en
127.0.0.1:8091, sin descargar otras revisiones. Ctrl+C detiene el motor.
No declara readiness por iniciar el proceso; desde otra terminal:

```bash
curl --fail http://127.0.0.1:8091/health
curl --fail http://127.0.0.1:8091/v1/models
python3 tests/run_golden.py
python3 -m unittest discover -v
```

Con el motor sano, arrancar el gateway existente en otra terminal:

```bash
python3 src/gateway_http.py
```

Gateway: 127.0.0.1:8092, `/healthz`, `/v1/capabilities`, `/v1/models` y
`/v1/chat/completions`. MCP: `python3 src/mcp_server.py` (stdio, motor en
8091); incorporación en `onboarding-consumidor-v1.md`. El instalador no
registra MCP automáticamente en aplicaciones ni crea un servicio de inicio.

Para las sondas hardware, añadir al PATH los directorios extraídos que
contienen llama-server/llama-tts y usar su LD_LIBRARY_PATH correspondiente;
los GGUF explícitos están en `run/build/wsl/cache/`. La batería se ejecutó;
los resultados están en `reviews/evidence/sondas-WSL-RTX2060-2026-11-04/`.

## Lectura del proyecto y límites

- I0 e I1 tienen evidencia previa en M2; la regresión se repitió en esta PC.
- El gateway actual ofrece texto/imagen a texto y validación estructurada.
  Su `/healthz` acredita el gateway; comprobar también el motor en 8091.
- Voz, transcripción, conversación por turnos y video pertenecen a I1-V,
  todavía pendiente. No se anuncian como capacidades instaladas.
- B-T8 conserva la errata documentada: rechazar `audio_url` no demuestra
  ausencia de ASR; la sonda previa acepta `input_audio`. El cambio de
  instalación no altera el golden ni el contrato v1.
- D-08 sigue pendiente para el producto. D-09 autorizó las pruebas de
  voz/cámara de esta sesión sin retención. D-10 pide transcripciones
  futuras para verificación; su implementación sigue pendiente.
- Exposición solo loopback. Piloto remoto, TLS, identidad, cuotas y UI son
  trabajo posterior del plan; no están instalados por este encargo.

Los resultados de esta sesión están en
`reviews/evidence/instalacion-wsl-2026-11-04/` y el reporte de revisión
en `reviews/2026-11-instalacion-wsl.md`.

La retoma personal y los siguientes pasos están en `retomar-dell-g7.md`.
