# ADR-006: Modalidades locales del artefacto vigente y streaming en loopback

```text
ADR-006: Las modalidades que el artefacto congelado ya soporta se
habilitan en loopback por gate (ampliación I1-V); SSE stdlib permitido
Estado: propuesto (ajuste del PLAN LFM3-2, Operador 2026-11-04: «corre
ronda adversarial del ajuste al plan para afinar y procede»); enmienda
ADR-005 en dos obligaciones; sin activación remota
Contexto: sondas de sesión (docs/reviews/2026-11-plan2-ajuste-
multimodal.md, P-1..P-11) muestran que llama-server 0.8.0 b11960 con el
modelo y mmproj registrados declara modalities vision/video/audio,
transcribe español exacto vía input_audio y acepta video; B-T8 era un
falso negativo (audio_url no existe en el formato OpenAI). ADR-005
obliga «capabilities jamás anuncia voz/video/streaming» y descartó
aiohttp porque «no hay streaming en I0/I1». El plan dejaba estas
modalidades en I6 (candidatos), atándolas a vigilancia remota sin
necesidad técnica, y el SSE local a I3 (MCP remoto).
Decisión:
  1. Enmienda de ADR-005: capabilities del gateway anuncia una modalidad
     (transcripcion, voz, video, streaming) sólo cuando su TAREA I1-V
     cerró su gate; antes sigue en false. Nunca se deriva de /props.
  2. Enmienda de ADR-005: SSE de texto sobre ThreadingHTTPServer stdlib
     permitido en I1-VR, sin buffering; la desconexión del cliente
     cancela la tarea del motor y el cupo no se libera antes de
     confirmarlo (log o /slots, verificado por el gate).
  3. Medios sólo como data URI/base64 en el gateway; URL http(s)/file
     → 400 sin llamar al motor.
  4. ffmpeg/ffprobe son dependencia de ejecución YA EXISTENTE del motor
     congelado (libmtmd los lanza desde PATH para video/audio de
     contenedor): se inventarían con versión y hash (I1-V0) y readiness
     de video falla cerrado si difieren del inventario.
Alternativas descartadas:
  - Dejar las modalidades en I6: exige candidato/promoción para algo
    que no cambia motor ni modelo; retrasa voz sin reducir riesgo.
  - aiohttp para SSE: dependencia nueva; ThreadingHTTPServer basta para
    loopback y un cliente por turno.
  - Habilitar audio/video directo en 8091 como superficie: sin
    validación de frontera ni límites; v1 lo prohíbe al consumidor.
Consecuencias:
  - Gana: voz y transcripción usables antes de I2, sin dependencias.
  - Pierde: hilos stdlib sostienen streams largos con concurrencia
    modesta; aceptable en loopback, revisable en I2 con D-04.
  - Queda obligado: rutas I1-V fuera de exposición remota salvo
    decisión explícita en I2-D; ADR-005 sigue vigente en lo demás.
```
