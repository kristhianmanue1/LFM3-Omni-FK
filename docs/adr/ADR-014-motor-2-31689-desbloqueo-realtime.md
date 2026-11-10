# ADR-014: Salto registrado del motor — par 2 (llama.cpp 54cde710) y
# desbloqueo de realtime

```text
ADR-014: salto registrado del motor según ADR-001: par 2 = llama.cpp
master commit 54cde710 (0.9.0-dev, construido de fuente, Metal
embebido) + LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M sin cambio (revisión
d508b88); llama-tts/ffmpeg/ffprobe siguen fijados por ADR-006 §4.
Estado: aceptado — encargo del Operador 2026-11-10 («debemos cambiar
el motor congelado ya que es un avance»; luego «ok adelante y hay
que hacer prueba directa conmigo como humano»).
Contexto: ggml-org/llama.cpp#31689 (voz de /v1/realtime sin
lang/voice) fue cerrado hoy vía PR #31982 (merge 203b5f4, fix
daf4b34). La cláusula de ADR-007 («si #31689 se corrige, reevaluar
realtime con operación registrada») queda disparada. La bottled
Homebrew 0.9.0 (verificada 2026-11-10) NO contiene el fix; sólo
master lo trae. Sonda diferencial con el binario candidato (puerto
aislado 8093, 2026-11-10): con --tts-lang es el re-ASR del audio
realtime es EXACTO al canal de texto («El paquete llega el martes a
las tres de la tarde.»), primer audio 0.44 s; sin el flag el modelo
no siguió la instrucción (control débil, no reproduce la frase).
RSS del candidato: 2.94 GB. Expediente:
docs/reviews/evidence/motor-2-31689/.
Decisión: adoptar el par 2 como pareja congelada. run/serve.sh
resuelve el motor con escalera de resolución: 1) override explícito
LFM3_MOTOR_BIN; 2) binario fijado HERMANO del repo (producción);
3) legado command -v, que conserva la hermeticidad de los tests con
árbol reubicado en fixture (RED: 5 fallos de suite en la primera
edición + 4 fallos de la clase EscaleraMotor, capturados en
red-escalera.txt del expediente). Las piernas 1 y 2 exigen SHA-256
igual al registrado (patrón del guard de hash de
src/gateway_http.py::_resolver_entorno_tts; hook
LFM3_MOTOR_SHA_REGISTRADO para fixtures); la pierna 3 emite AVISO en
stderr y nunca pasa en silencio, y la línea arriba nombra el binario
resuelto. El curl del readiness se ancla antes del export de PATH
(pierna 2 sin curl propio: sin el ancla, un motor ajeno en 8091
podría responder el readiness). Añade --tts-lang es (inerte para el
contrato v1: el 8091 no oferta voz; alinea el default de
/v1/audio/speech del motor con ADR-007) y /opt/homebrew/bin al PATH
del runbook para que ffmpeg/ffprobe/llama-tts (ADR-006 §4) sigan
resolviendo (alarma r16b atendida con registro, no en silencio).
tools/inventario_motor.py comparte la escalera, sus predicados y el
guard. Cambiar de nuevo el motor o el modelo sigue siendo operación
registrada (ADR-001).
Alternativas descartadas:
  - brew upgrade a 0.9.0: sin el fix (#31689 sigue presente ahí).
  - Permanecer en 0.8.0: deja la cláusula de ADR-007 sin ejecutar y
    el realtime bloqueado a nivel motor, contra el encargo explícito.
  - Construir también llama-tts del mismo commit: churn sin
    necesidad; la evidencia P-9 (re-ASR exacto) es de llama-tts
    0.8.0, que sigue fijado por ADR-006 §4.
Consecuencias:
  - Gana: realtime usable en español a nivel motor; su ANUNCIO
    contractual es tarea con gate propia y NO sucede en esta
    operación (capabilities siguen declaradas por SPEC).
  - Pierde: la batería B-T1..B-T12 se re-ejecuta contra el par 2 y
    puede revertir comportamientos documentados de 0.8.0 (B-T8 es
    alarma de cambio contractual, jamás se deshabilita); el binario
    ya no es bottled: la reproducibilidad queda anclada al commit
    54cde710 + SHA-256 del artefacto en el expediente.
  - Queda obligado: f0 conserva el par 1 como registro histórico de
    F0; la tabla de deltas de comportamiento 0.8.0 -> 54cde710 vive
    en el expediente de evidencia; toda desviación incompatible
    respecto al contrato v1 vive en v2 (herencia ADR-001).
```
