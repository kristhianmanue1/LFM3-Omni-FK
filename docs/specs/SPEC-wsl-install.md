# Instalación local en WSL2 — mismo artefacto

## Encargo y alcance

TAREA WSL-INSTALL, 2026-11-04. El Operador pide analizar el repositorio
e instalarlo aquí. Clase Architectural: se añade un instalador para Linux.
Base: main@9c0035bbd831822f9dcc4894d3619e2ac3546cc0, recuperada mediante
el conector GitHub porque la terminal no tiene red. Los 154 blobs se
contrastaron con sus hashes Git. `.git` es una reserva de solo lectura;
esta copia es un snapshot verificado, no un clon con historial.

Plan de referencia: `docs/roadmap/pruebas-hardware.md`, ruta WSL2/CUDA;
no se amplía PLAN-2 ni se promueve ninguna iteración pendiente.

Permitido: recuperar fuente; añadir instalador/arranque WSL y sus pruebas;
registrar análisis y evidencia; descargar los artefactos exactos previstos
por el plan dentro de `run/build/wsl/`; ejecutar pruebas locales.
Superficie: terminal y conector GitHub; lectura de herramientas instaladas;
escritura en este workspace y /tmp; descarga de GitHub/ggml-org/llama.cpp
y Hugging Face/LiquidAI; inferencia solo en 127.0.0.1:8091/8092.
Prohibido: push, publicaciones, cambios globales, tocar otros proyectos,
cambiar versiones, exponer LAN, usar cámara/micrófono o ampliar I1-V.
Parada: instalación verificada o bloqueo externo diagnosticado y registrado.
No se consumen APIs de inferencia tarifadas.

## Requisitos y decisiones

- REQ-W1: b11960, commit 8642541b255bfb5dc39cd351a178be09013a55d6,
  binarios oficiales Ubuntu x64 CUDA 12.8 y su paquete cudart. Procedencia:
  plan hardware y release oficial b11960 consultada en esta sesión.
  CUDA 12.8 evita elegir el paquete 13.4 más reciente de la misma release;
  compatibilidad con el driver local queda pendiente de prueba real.
- REQ-W2: pesos Q4_K_M y mmproj Q4_0 de HF
  d508b88f08a5b4286f2d2805a6a8d69a0ff44c72; SHA-256 de la línea base M2.
  No se usa `-hf`, main ni latest. Toda descarga falla ante hash incorrecto.
- REQ-W3: instalación local sin sudo ni paquetes Python; descarga temporal
  y publicación por rename; exclusión mutua del instalador mediante flock.
  Archivo comprimido extraído con filtro data en un directorio nuevo.
- REQ-W4: arranque en primer plano, greedy, reasoning off, GPU explícita,
  alias contractual y loopback. Entorno LLAMA_ARG_* eliminado. Parada por
  Ctrl+C; `run/stop.sh` puede identificar el binario real en puerto 8091.
- REQ-W5: versión/build/commit y hashes se verifican antes de arrancar.
  `llama-server` y `llama-tts` deben existir. El inventario local registra
  los hashes de todos los archivos extraídos y se contrasta al arrancar.
  No se ofrece readiness hasta probar /health y /v1/models desde fuera.

Amenazas: descarga corrupta, path traversal de tar, symlinks fuera del
destino, instalación concurrente y cambios en runtime. Controles: hashes
fijados, tar data_filter, staging nuevo, flock y manifiesto de integridad.
El manifiesto es evidencia local, no atestación ante un atacante del mismo
usuario. Kill switch: Ctrl+C en el proceso del motor; no se crea autostart.

DoD: artefactos presentes y verificados; versión exacta; GPU detectada;
salud/modelo/inferencia reales; golden y suite en verde; cinco gates;
revisión fresca. Los bloqueos de red/GPU/sockets impiden cerrar el DoD.
RED/GREEN aplica a integridad y extracción; la copia de fuentes es
restauración de archivos existentes, sin cambio de comportamiento.

## Análisis del estado previo

I0/I1 están registrados como accepted_local en la máquina M2. En esta PC
no acreditan instalación ni capacidades activas. El gateway 8092 ofrece
texto/imagen, rechaza campos desconocidos y valida salidas estructuradas.
MCP stdio usa el motor 8091. Audio/video/voz no están activos en el gateway.
B-T8 conserva el falso negativo documentado en el ajuste I1-V0; instalar no
lo corrige ni habilita modalidades. D-08 y D-09 siguen pendientes.

El inventario existente busca caché HF/Homebrew; para esta instalación se
usa el manifiesto WSL explícito, sin modificar esa herramienta ni ADR-001.
AN-KLA no está instalado y `.an-kla/` no existe: el historial se reconstruye
desde docs versionados, sin crear memoria ni afirmar verificación AN-KLA.
