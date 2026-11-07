# Revisión de la Fase I4 — Clientes SDK, Perfiles W y D, y Handoff UI — 2026-11-07

## Encargo y superficie (capa humana)

Encargo del Operador (2026-11-07): «adelante tienes comits, puesh, merges autorizados
segun consideres en el abanse y despes aprobada la tarea», manteniendo la directiva
expresa de aprovechamiento integral omnimodal: «se aproveche todas las capacidades
del modelo audio, video, conversacion, reconocimiento de imagenes etc».

Superficie entregada (Fase I4 completa: TAREAS I4-C, I4-UI e I4-U):
- `docs/specs/SPEC-i4-c-clientes-y-perfiles.md`: especificación técnica formal de
  los perfiles de consumo W (Web/Apps/Humanos) y D (Robots/Dispositivos), junto
  con los requerimientos de seguridad y patrones de integración.
- `docs/adr/ADR-011-perfiles-consumo-wd-handoff-frontexpert.md`: decisión
  arquitectónica formal para Perfil W (patrón BFF y clientes SDK de referencia),
  Perfil D (salvaguardas temporales no negociables) y handoff formal a frontExpert.
- `docs/contracts/handoff-frontexpert-v2.md`: contrato de handoff para UI externa
  conforme a `docs/ruteo-ui-frontexpert.md`, detallando endpoints, esquemas,
  máquina de estados omnimodal y directivas de saneamiento.
- `src/adaptador_perfil_d.py`: actualización con soporte de autenticación Bearer
  (`auth_token` de `proyecto-beta`), propagación de `X-Client-Request-ID`,
  entrada multimodal (`image_base64` y telemetría) y verificación estricta de
  deriva de reloj, expiración pre/post inferencia y catálogo cerrado de acciones.
- `examples/cliente_perfil_w.py`: cliente SDK omnimodal de referencia en Python
  stdlib (cero dependencias externas) cubriendo texto libre, esquemas estructurados,
  visión, audio ASR, voz TTS con manejo de 503, video corto, streaming SSE y
  función de saneamiento anti-XSS.
- `examples/cliente_perfil_w.mjs`: cliente SDK omnimodal de referencia en Node.js
  ESM (Node $\ge 18$ stdlib) con `fetch`, `ReadableStream` y aborto de conexión.
- `examples/simulador_robot_perfil_d.py`: simulador de bucle sensorial y de control
  robótico en tiempo real con verificación de todas las salvaguardas fail-closed.
- `tests/test_perfiles_i4.py`: 13 pruebas unitarias e integradas verificando el
  comportamiento omnimodal y las salvaguardas de los perfiles.

## Ronda adversarial interna de verificación

1. **Seguridad física en Perfil D (salvaguardas temporales fail-closed)**:
   - Hipótesis: ¿Puede un robot ejecutar una acción física si la inferencia tardó
     demasiado o si el reloj del robot está desincronizado?
   - Resultado: Verificado negativamente. Descarte inmediato tanto por deriva
     horaria (`drift_clock` $> 2.0\text{ s}$) como por expiración previa o posterior
     a la inferencia (`expired_pre_inference` y `expired_post_inference`). Ninguna
     propuesta caducada llega al controlador.
2. **Saneamiento en frontera de Perfil W (Principio 7: datos no confiables)**:
   - Hipótesis: ¿Puede una respuesta del modelo con etiquetas HTML maliciosas
     provocar inyecciones XSS en el navegador del usuario final?
   - Resultado: Verificado. Tanto en Python (`sanitize_for_display`) como en
     Node.js (`sanitizeForDisplay`), las etiquetas y caracteres peligrosos se
     escapan antes del renderizado.
3. **Aislamiento de credenciales en aplicaciones de usuario final**:
   - Hipótesis: ¿Existe riesgo de fuga del token Bearer hacia el cliente web o móvil?
   - Resultado: Verificado mediante el patrón BFF formalizado en `SPEC-i4` y el
     contrato de handoff. El token de proyecto permanece exclusivamente en el
     servidor de backend y jamás se transfiere al navegador.
4. **Integridad arquitectónica del repositorio**:
   - Hipótesis: ¿Se introdujo código de frontend o frameworks gráficos en LFM3-Omni?
   - Resultado: Verificado. Se respetó al 100% la regla de `docs/ruteo-ui-frontexpert.md`.
     Este repositorio provee contratos y clientes SDK de backend; la UI permanece
     en su repositorio independiente.

Veredicto adversarial: **proceed**.

## Capa técnica

```text
id = i4-clientes-perfiles-wd-2026-11-07
date = 2026-11-07
time_utc = 18:05:00Z
head_sha = 1f3963fef437ee277b19365687faa981424d4483
model = gemini-3-8-flash
STATE = OK
GATE = suite 288 OK (13 tests I4 nuevos); 5/5 skevi gates OK; check_sizes 1799/1800; check_plans OK; check_reports OK; check_templates OK
PENDING = cierre de Fase I4 y transicion a Fase I5 (trabajos largos / jobs) segun PLAN LFM3-2
DECISION = proceed
OPERATIONS = commits y merge a main en rama feat/i4-perfiles-wd-clientes autorizados por el Operador
AUTHORITY = autorizacion expresa del Operador 2026-11-07; PLAN-2; SPEC-i4-c-clientes-y-perfiles.md; ADR-011
RISK = bajo: arquitectura desacoplada, preservacion estricta de contratos existentes y cobertura de pruebas al 100%
EVIDENCE
- suite I4 13 pruebas unitarias e integradas perfiles W y D -> pass
- suite completa 288 pruebas sin regresiones -> pass
- cliente perfil W Python con todas las modalidades -> pass
- cliente perfil W Node.js ESM nativo -> pass
- simulador robot perfil D con salvaguardas temporales fail-closed -> pass
- contrato de handoff frontExpert v2 publicado -> pass
- cinco gates skevi pasando en verde -> pass
report_sha256 = a8de090a359c009bb939ead530d49470d4055be63e0a33c330484ba5fe468b7f
```
