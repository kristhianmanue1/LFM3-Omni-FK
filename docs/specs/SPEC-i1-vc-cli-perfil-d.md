# SPEC-i1-vc — CLI unificado y adaptador local de perfil D (robots)

> Cubre: TAREA I1-VC del PLAN LFM3-2. Formato: 02 §2.2. Decisiones normativas:
> ADR-008 (§3), perfil D (docs/contracts/perfiles-servicio-v2.md), y
> principios 5 (fail-closed) y 7 (datos no confiables). Loopback sobre el
> gateway 8092. Sin dependencias externas (Python 3.12+ stdlib).

```text
SPEC-i1-vc [cubre: I1-VC, ADR-008, perfil D]
Comportamiento:
  1. CLI unificado stdlib (src/cli.py): entrypoint unificado por línea de
     comandos para humanos y scripts contra el gateway HTTP 8092
     (LFM3_GATEWAY_URL / LFM3_GATEWAY_PORT); provee subcomandos para
     salud (health), texto (text), visión (vision), audio (audio),
     síntesis de voz (speech) y video (video), con soporte de pipes stdin
     y emisión de JSON estructurado (--json).
  2. Adaptador local perfil D (src/adaptador_perfil_d.py): interfaz para
     dispositivos y simuladores de robots que traduce observaciones
     sensoriales a propuestas de acción evaluadas por el modelo; aplica
     estrictamente las salvaguardas de tiempo real del perfil D antes
     y después de consultar al gateway:
     - Margen de deriva de reloj <= 2.0 s (|now - observed_at| <= 2.0 s).
     - Descarte pre-inferencia si now >= expires_at o observed_at >= expires_at.
     - Descarte post-inferencia si el tiempo de inferencia superó expires_at.
     - Deduplicación y orden monotónico por observation_id (rechazo de
       duplicados y reordenamientos).
     - Descarte si la inferencia está incompleta (finish_reason != "stop").
     - Validación de propuesta contra enum cerrado de allowed_kinds.
     - Aislamiento seguro: sin actuadores físicos; modo simulador.

Entradas CLI (src/cli.py):
  lfm3-cli health [--json]
  lfm3-cli text <prompt | - > [--schema SCHEMA] [--max-tokens N] [--json]
  lfm3-cli vision --image FILE_O_B64 <prompt> [--schema SCHEMA] [--json]
  lfm3-cli audio --audio FILE_O_B64 <prompt> [--schema SCHEMA] [--json]
  lfm3-cli speech <input | - > [--output OUT_WAV] [--voice V] [--speed S]
  lfm3-cli video --video FILE_O_B64 <prompt> [--schema SCHEMA] [--json]

Entradas Adaptador Perfil D (src/adaptador_perfil_d.py):
  evaluar_observacion(solicitud, gateway_url=...):
    device_id: string (1..64)
    observation_id: string (1..64)
    observed_at: string ISO 8601 UTC
    expires_at: string ISO 8601 UTC
    prompt: string (1..8000)
    image_base64: string opcional (PNG/JPEG)
    allowed_kinds: list[string] (enum cerrado de acciones autorizadas)

Salidas Adaptador Perfil D:
  Aceptada: {
    "status": "accepted",
    "observation_id": string,
    "request_id": string,
    "complete": true,
    "proposal": {"kind": string, "payload": dict},
    "observed_at": string,
    "expires_at": string,
    "latency_s": float
  }
  Descartada: {
    "status": "discarded",
    "reason": "drift_clock" | "expired_pre_inference" |
              "expired_post_inference" | "duplicate_observation" |
              "reordered_observation" | "incomplete_output" |
              "unauthorized_proposal_kind" | "invalid_schema" | "gateway_error",
    "observation_id": string,
    "detail": string
  }

Casos:
  - DADO un comando de texto por CLI CUANDO se pasa prompt ENTONCES
    responde el texto del gateway o JSON si --json está activo.
  - DADO un pipe stdin a CLI CUANDO se redirige a text o speech ENTONCES
    procesa el stream de entrada correctamente.
  - DADO una observación de robot con reloj desfasado > 2.0 s CUANDO
    se evalúa ENTONCES status: discarded, reason: drift_clock.
  - DADO una observación ya caducada (now >= expires_at) CUANDO se evalúa
    ENTONCES status: discarded, reason: expired_pre_inference, sin llamar
    al gateway.
  - DADO una observación con expires_at muy corto (ej. 50 ms) CUANDO la
    inferencia tarda más que ese plazo ENTONCES status: discarded,
    reason: expired_post_inference, sin aplicar propuesta.
  - DADO una observación repetida con el mismo observation_id CUANDO
    se reenvía ENTONCES status: discarded, reason: duplicate_observation.
  - DADO una observación con proposal.kind fuera de allowed_kinds
    ENTONCES status: discarded, reason: unauthorized_proposal_kind.
```
