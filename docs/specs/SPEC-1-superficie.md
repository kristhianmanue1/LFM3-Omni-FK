# SPEC-1 — Superficie de inferencia (especificación)

> Cubre: REQ-1, REQ-2, REQ-3, REQ-5, REQ-6, REQ-7, REQ-8 del F0.
> Formato: 02 §2.2. Casos trazados a la batería B-T1..B-T12 de
> docs/verificaciones-motor.md; cada caso será un test del golden set
> (F2-2). El contrato de esta frontera es
> docs/contracts/superficie-inferencia-v1.md.

```text
SPEC-1 [cubre: REQ-1, REQ-2, REQ-3, REQ-5, REQ-6, REQ-7, REQ-8]
Comportamiento: el servicio responde en localhost:8091 con salud,
  descubrimiento de modelo y chat multimodal (texto y visión) con tools
  y salida forzada a esquema JSON, bajo muestreo greedy, fail-closed en
  la frontera, recursos acotados (REQ-5) y cláusula de licencia
  declarada (REQ-8); disponible como superficie consumible por terceros
  del ecosistema (web, apps) según el contrato v1.
Entradas: las del contrato v1 (messages text/image_url, tools,
  response_format, max_tokens recomendado 1..4096 — el build no valida
  el rango). Fail-closed estructural: JSON malformado, messages ausente
  o partes de contenido desconocidas se rechazan con 400; campos
  top-level desconocidos se ignoran con 2xx — validar el payload es del
  lado consumidor.
Salidas: las del contrato v1 (content, tool_calls, usage, timings).
Errores:
  400 entrada malformada o no soportada — estado: sin efecto lateral
  503 motor cargando — estado: reintentable (no ejercitado por batería;
    comportamiento estándar del build)
Modelo de estados (02 §5):
  ESTADOS: parado, cargando, listo
  TRANSICIONES:
    parado --arranque (runbook ADR-001)--> cargando
    cargando --modelo en memoria--> listo
    listo --parada (run/stop.sh)--> parado
  INVARIANTES:
    - durante cargando, /health responde 503 (reintentable); nunca 200
    - la carga no termina en tiempo operativo -> fallo explícito del
      operador (parado), jamás éxito inferido
Casos:
  - DADO el servicio arrancado por el runbook (ADR-001) CUANDO GET
    /health ENTONCES HTTP 200 con {"status":"ok"} (B-T1)
  - DADO el servicio arriba CUANDO GET /v1/models ENTONCES la lista es
    exactamente ["LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M"] (B-T2)
  - DADO un request con response_format json_schema
    {nombre:string, edad:integer} CUANDO se pide registrar a una persona
    ENTONCES content parsea como JSON y cumple ambos tipos (B-T3)
  - DADO el mismo prompt enviado 3 veces CUANDO el muestreo es greedy
    ENTONCES las 3 salidas son idénticas byte a byte (B-T4)
  - DADO 3 corridas de 64 tokens con 20 s de separación CUANDO se mide
    predicted_per_second ENTONCES la mediana es >= 15 tok/s (B-T5)
  - DADO tools con get_weather(city:string) y tool_choice:"auto" CUANDO
    se pregunta el clima de una ciudad ENTONCES tool_calls[0].function
    es get_weather con arguments JSON que parsea (B-T6)
  - DADO un request con image_url data URI de un PNG uniforme rojo
    CUANDO se pregunta el color ENTONCES la respuesta contiene
    "rojo" o "red" (B-T7)
  - DADO un request con parte {type:"audio_url"} en chat CUANDO se
    envía ENTONCES HTTP 400 "unsupported content[].type" — caso de
    regresión contractual del límite conocido del build (B-T8)
  - DADO un cuerpo JSON malformado o sin messages CUANDO se envía
    ENTONCES HTTP 400 con {error:{code,message,type}} (B-T9)
  - DADO el modelo cargado CUANDO se mide el RSS residente del proceso
    ENTONCES es < 4 GB (B-T10)
  - DADO el contrato publicado CUANDO se busca la cláusula de licencia
    ENTONCES cita REQ-8 y EV-10 (B-T11)
  - DADO el servicio arriba CUANDO se listan los sockets en escucha del
    puerto ENTONCES solo aparece 127.0.0.1:8091 (B-T12)
Invariantes:
  - Escucha solo en 127.0.0.1:8091 (CERRADA-6; verificación B-T12)
  - Toda salida persistida o reenviada pasa por validación contra
    esquema cerrado antes (REQ-7)
  - La salida del modelo nunca se interpreta como instrucción
    (principio 7; guía 06 §5)
  - Ningún consumidor recibe contenido que el contrato v1 no declara
  - El RSS residente con el modelo cargado se mantiene < 4 GB (REQ-5)
```

## Trazabilidad caso ↔ batería ↔ REQ

| Caso de SPEC | Batería | REQ |
|---|---|---|
| salud | B-T1 | REQ-1, REQ-2 |
| modelo servido | B-T2 | REQ-1 |
| esquema cerrado | B-T3 | REQ-7 |
| determinismo greedy | B-T4 | REQ-6 |
| throughput | B-T5 | REQ-3 (umbral contractual) |
| tool calling | B-T6 | REQ-3, REQ-4 (base de SPEC-2) |
| visión | B-T7 | REQ-3 |
| audio rechazado en chat | B-T8 | REQ-1 (límite conocido) |
| frontera fail-closed | B-T9 | REQ-7 |
| RSS acotado | B-T10 | REQ-5 |
| cláusula de licencia | B-T11 | REQ-8 |
| binding exclusivo | B-T12 | REQ-2 |

Nota: REQ-3 y REQ-8 se cubren además por las cláusulas del propio
contrato v1 (secciones Entrada/Invariantes); los casos B-T11 y B-T12
hacen binaria esa cobertura.
