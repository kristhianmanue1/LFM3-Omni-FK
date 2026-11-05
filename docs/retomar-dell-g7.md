# Retomar pruebas en Dell G7 7700

La sesión personal terminó con goodbye. No hay capturas activas; el motor
8091 queda bajo control de su terminal original. Informe:
[cierre Dell G7](reviews/2026-11-dell-g7-7700.md).

## Estado verificado

- Dell G7 7700, i7-10750H, RTX 2060 de 6144 MiB, 16 GB host;
  WSL2 Ubuntu 24.04.5 ve ~9.7 GiB. Python 3.12.3.
- Driver Windows 621.14; llama.cpp b11960/8642541b2, CUDA 12.8.
  El driver 556.12 produjo unsupported PTX toolchain.
- Q4_K_M + mmproj Q4_0, revisión HF
  d508b88f08a5b4286f2d2805a6a8d69a0ff44c72; hashes en
  `../run/wsl-artifacts.json`. Retomar no exige actualizar artefactos.
- Gateway I1 sigue en texto/imagen; estos ejemplos son exploratorios
  contra el motor directo, sin promover gates I1-V ni contrato nuevo.

Datos automáticos: `reviews/evidence/sondas-WSL-RTX2060-2026-11-04/`.
`resultados.json` contiene mediciones; `pruebas-interactivas.json` resume
salidas de herramientas y confirmaciones del Operador. No contiene el
contenido de conversaciones: no se guardaron transcripciones ni medios
personales y no se pueden reconstruir retrospectivamente.

## Antes de la próxima prueba personal

1. Leer AGENTS y decisiones D-09/D-10. Implementar D-10 antes de volver
   a abrir dispositivos para verificación: conservar entrada transcrita,
   texto de respuesta, identificador de turno, tiempos y hashes/parámetros.
2. Realtime recibió el audio original; una transcripción auxiliar debe
   distinguirse de un transcript nativo y no presentarse como tal.
3. Guardar texto sólo localmente en archivos 0600 bajo
   `docs/reviews/evidence/privado/transcripciones/`, excluido de Git.
   No hay borrado automático acordado. Audio/video no están autorizados
   para retención por esta decisión. Publicar extractos sólo tras revisión
   y saneamiento con el Operador.
4. Probar persistencia, asociación de turnos, cancelación, permisos e
   ignores; revisión fresca y gates. Los ejemplos publicados conservan
   la versión probada sin transcripciones: D-10 sigue sin implementar.

AN-KLA no está instalado ni se inicializó memoria. Este documento es
el punto de retoma; no hay una memoria AN-KLA verificada.

## Motor y regresión

```bash
python3 scripts/install_wsl.py --check
curl --fail http://127.0.0.1:8091/health
```

Si no está activo, `python3 scripts/install_wsl.py --serve` lo arranca
en primer plano. No duplicar arranque si el puerto ya sirve el modelo.
En otra terminal: `python3 tests/run_golden.py` y
`python3 -m unittest discover -v`.

Las sondas sintéticas requieren los binarios runtime en PATH y sus
librerías en LD_LIBRARY_PATH; pasar a `tests/sondas_multimodal.py` los
dos GGUF con `--modelo`, `--mmproj` y un directorio NUEVO con `--salida`.
No sobrescribir esta evidencia ni regenerar fixtures de macOS en WSL.
Instalación: `instalacion-wsl.md`.

## Ejemplos conservados

Tras implementar D-10 y con una prueba solicitada por el Operador:

```bash
LFM3_CONSENTIMIENTO_D09=si python3 examples/wsl/continuous_unlimited.py
```

| Archivo en examples/wsl/ | Prueba |
|---|---|
| live_voice.py | español: micrófono 10 s, ASR/chat y llama-tts es |
| live_video.py | cámara 4 s sin audio, descripción y voz española |
| realtime_english.py | un turno nativo inglés y salida en streaming |
| continuous_english.py | versión acotada de 180 s / 6 turnos |
| continuous_unlimited.py | sin límite global; termina con goodbye o Ctrl+C/SIGTERM |

Todos requieren consentimiento D-09 al ejecutarlos. Requieren WSLg
PulseAudio, ffmpeg/ffplay/pacat y acceso a /dev/video0 para cámara.
La ACL de cámara se verificó en esta sesión; no asumir que persiste al
reiniciar. Importaciones y tests no abren dispositivos.

La conversación usa turnos automáticos: pausa de 1 s, máximo 20 s de
entrada por intervención, máximo 30 s de voz de salida y timeouts por
operación. Micrófono cerrado durante reproducción; no se probó barge-in
ni full-duplex. Un lector separado responde PING/PONG durante el silencio.

## Qué falta verificar

La conservación de contexto fue un veredicto humano sin transcripciones.
Primer PCM excluye captura, VAD y subida: no es latencia fin-a-fin ni
p95/SLO. Rendimiento no comparado en condiciones controladas con M2.
Inglés nativo funcionó; realtime español y ADR-007 conservan sus límites.
