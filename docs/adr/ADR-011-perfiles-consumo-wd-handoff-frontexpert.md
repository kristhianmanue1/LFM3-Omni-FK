# ADR-011: Perfiles de consumo W y D, clientes SDK de referencia y handoff formal para frontExpert

```text
ADR-011: Perfiles de consumo W (Web/Apps/Humanos) y D (Dispositivos/Robots), clientes
SDK de referencia omnimodales (Python y Node.js) y handoff formal a frontExpert.
Estado: aceptado (formalizado en TAREA I4-C/I4-UI, PLAN LFM3-2; 2026-11-07)
Contexto:
  - Tras la entrega del servidor MCP remoto en I3, la Fase I4 establece el consumo
    de la plataforma desde sistemas cliente externos: aplicaciones de usuario final
    (Perfil W) y agentes físicos o simulados (Perfil D).
  - La directiva del Operador requiere que se aprovechen integralmente todas las
    capacidades omnimodales del modelo (texto, visión, audio, voz, video y
    conversación por turnos).
  - La regla registrada en docs/ruteo-ui-frontexpert.md prohíbe alojar código de
    interfaz gráfica dentro de este repositorio; las interfaces visuales se
    construyen en repositorios independientes sobre frontExpert (contrato v2)
    con Skevi como método.
  - Retos de seguridad y diseño:
    1) Perfil W: riesgo de fuga de tokens y ataques de inyección si el navegador
       o app accede directamente al motor sin mediación.
    2) Perfil D: riesgo de daño físico o decisiones erróneas si un robot actúa
       sobre información sensorial caducada, respuestas truncadas o acciones no
       autorizadas.
    3) Heterogeneidad de clientes: necesidad de clientes de referencia en Python
       y JavaScript/Node.js sin dependencias externas pesadas.
Decisión:
  1. Perfil W (Arquitectura BFF y clientes SDK de referencia):
     - El consumo web o móvil se realiza mediante el patrón Backend-For-Frontend
       (BFF). El navegador o app móvil nunca recibe los tokens Bearer del servicio.
     - Se entregan clientes de referencia de alta fidelidad:
       * examples/cliente_perfil_w.py: implementación completa en Python stdlib.
       * examples/cliente_perfil_w.mjs: implementación completa en Node.js ESM
         usando fetch nativo y ReadableStream para SSE.
     - Cobertura omnimodal completa en ambos clientes:
       * Inferencia de texto libre y esquemas estructurados (JSON Schema v2-ext).
       * Percepción visual sobre imágenes (JPEG/PNG en base64).
       * Transcripción de audio (WAV 16 kHz en base64).
       * Síntesis de voz (TTS WAV 24 kHz) con manejo de error 503 tts_busy.
       * Video corto temporal (MP4 en base64).
       * Conversación interactiva con streaming SSE y cancelación reactiva.
     - Saneamiento en frontera: función de escapado HTML defensivo en ambos clientes
       para prevenir inyecciones XSS en el renderizado web de la salida del modelo.
  2. Perfil D (Dispositivos y robótica):
     - src/adaptador_perfil_d.py se actualiza para soportar autenticación Bearer
       (proyecto-beta) y transporte HTTPS/HTTP.
     - Salvaguardas fail-closed en tiempo real estrictas e inviolables:
       * Deriva de reloj máxima: 2.0 s.
       * Expiración pre-inferencia: descarte si ahora >= expires_at.
       * Expiración post-inferencia: descarte si el tiempo de cómputo sobrepasó
         expires_at (impide aplicar propuestas desfasadas).
       * Deduplicación de observation_id y verificación de orden monotónico.
       * Descarte de salida incompleta (finish_reason != 'stop').
       * Validación estricta contra lista blanca cerrada (allowed_kinds).
     - examples/simulador_robot_perfil_d.py verifica todo el bucle sensorial y de
       control en modo simulado seguro, sin efectos sobre actuadores físicos.
  3. Handoff a frontExpert (TAREA I4-UI):
     - Se publica docs/contracts/handoff-frontexpert-v2.md con las especificaciones
       completas para el equipo de frontend: endpoints, esquemas tipados, manejo de
       estados de conversación (idle, listening, thinking, speaking), y consumo
       seguro a través del BFF.
Consecuencias:
  - Positivas:
    * Se cubre el 100% de las modalidades omnimodales tanto en Python como en JS.
    * Los consumidores disponen de código de referencia verificado y ejecutable.
    * Se garantiza la seguridad física en robótica mediante descarte temporal estricto.
    * Se mantiene la integridad arquitectónica al no mezclar código UI en este repo.
  - Negativas / Mitigaciones:
    * El streaming SSE en Node.js requiere Node >= 18; mitigación: es la versión
      LTS soportada estándar en la industria.
    * La gestión de latencia en robots requiere sincronización horaria precisa (NTP);
      mitigación: el descarte ante deriva > 2.0 s protege contra desincronización.
```
