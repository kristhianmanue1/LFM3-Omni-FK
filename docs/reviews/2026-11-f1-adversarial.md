# Ronda adversarial F1 — registro (2026-11-02)

> Registro de la ronda adversarial de cierre de F1, conforme a ADR-037:
> la propuesta remite, el registro cuenta. Ejecutor de la ronda:
> subagente independiente con contexto fresco real
> (sesión ses_e6131bb42ffeHtgupnXmuINpFx, solo lectura).
> Alcance: los 11 artefactos de diseño contra F0, batería B-T*,
> restricciones vigentes y formatos de 02.

## Veredicto de la ronda

**BLOQ** — 2 hallazgos BLOQ (ítems literales del gate de F1: REQ-5 y
REQ-8 imprescindibles sin SPEC; frontera MCP con manifiesto que declara
un contrato inexistente), 5 MAYOR, 6 MENOR. Ninguno exigía re-medir el
motor: todos declarativos o de trazabilidad.

## Hallazgos y disposición

| # | Sev. | Dim. | Síntesis | Disposición aplicada |
|---|---|---|---|---|
| 1 | BLOQ | B | REQ-5 y REQ-8 imprescindibles sin SPEC (02 §2.2, gate ítem 1) | SPEC-1 ampliada a cubrir REQ-5/REQ-8; casos nuevos B-T10 y B-T11; trazabilidad actualizada |
| 2 | BLOQ | F | Manifiesto declara contrato mcp-tools inexistente; frontera MCP sin CONTRATO (gate ítem 2) | Creado docs/contracts/mcp-tools-v1.md; publica: v1 en ambos |
| 3 | MAYOR | C | REQ-5 trazado a B-T5 (throughput), que no prueba su criterio | B-T10 creado (RSS < 4 GB bajo carga); traza corregida; B-T5 re-trazado a REQ-3 (umbral contractual) |
| 4 | MAYOR | C | Invariante de binding citaba B-T1, que solo prueba respuesta, no exclusividad | Fuente cambiada a CERRADA-6 + runbook; caso binario nuevo B-T12 (lsof, pass) |
| 5 | MAYOR | B/C | Contrato sin CORS ni límites; manifiesto sobre-afirma | Contrato declara CORS (aviso del log) y límites (128k×4 slots, max_tokens 1..4096); manifiesto queda sincronizado |
| 6 | MAYOR | C | Invariante citaba /v1/realtime sin declararlo ni verificarlo | Voz declarada FUERA de la frontera v1; entrada exige v2; sonda F3-3 queda como verificación de capacidad, no contractual |
| 7 | MAYOR | D | Identificadores de tools/campos MCP en español violan convención de idiomas | Renombrados: health, infer_text, infer_vision, schema, image_base64 (SPEC-2 + contrato mcp-tools) |
| 8 | MENOR | A | Falta tabla de trazabilidad exigida por el plan; REQ-2 sin traza | Tabla caso↔batería↔REQ añadida a SPEC-1; B-T1 traza REQ-1+REQ-2 |
| 9 | MENOR | E | "Texto crudo" sin oráculo binario | Reescrito: validado==false y contenido string no vacío, sin validación ni transformación |
| 10 | MENOR | E | Predicado de visión más estricto que su par HTTP | Alineado: contiene "rojo" o "red" |
| 11 | MENOR | F | Manifiesto desfasado (pendiente-F1; "diseño en F1") | publica: v1/v1; ofrece: diseño cerrado, implementación F3-1 |
| 12 | MENOR | C | Capacidades declaradas sin respaldo de batería | Marcadas "no ejercitado por batería (estándar del build)": JPEG, max_tokens, 503, slot libre |
| 13 | MENOR | A | Ciclo de vida sin máquina de estados (02 §5) | Bloque ESTADOS/TRANSICIONES/INVARIANTES añadido a SPEC-1 |

## Verificación del recierre

- Los tres casos nuevos de batería se midieron tras las correcciones:
  B-T10 pass (RSS 23 MiB residente bajo carga; 2.78 GiB máximo
  observado en warmup — matiz mmap registrado), B-T11 pass (contrato
  cita REQ-8 y EV-10), B-T12 pass (único socket 127.0.0.1:8091).
- Batería actualizada: 12 pass / 1 fail conocido (B-T8), en
  docs/verificaciones-motor.md §2 y §7.
- Los cinco MAYOR entran en el mismo pase porque tocan el contrato y
  los nombres que F3 va a codificar (disposición de la ronda).
- Sin re-medición del motor: ninguna capacidad afirmada nueva.

## Estado resultante

Con las disposiciones aplicadas, los dos ítems BLOQ del gate quedan
cubiertos (SPEC para todo REQ imprescindible; contrato para toda
frontera externa). La fase F1 puede recerrarse en OK con evidencia.
