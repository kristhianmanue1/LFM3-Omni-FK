#!/usr/bin/env python3
"""Adaptador local del perfil D (robots y dispositivos) para LFM3-Omni.

Contrato: docs/contracts/perfiles-servicio-v2.md (§D) · SPEC: docs/specs/SPEC-i1-vc-cli-perfil-d.md
Decisiones normativas: ADR-008 (§3), principios 5 (fail-closed) y 7 (datos
no confiables).
Aplica salvaguardas de tiempo real antes y después de la inferencia:
- Margen de deriva de reloj <= 2.0 s.
- Descarte pre-inferencia de observaciones vencidas.
- Descarte post-inferencia de propuestas que caducaron durante el cómputo.
- Deduplicación y orden monotónico por observation_id.
- Descarte de salidas incompletas (finish_reason != 'stop').
- Validación de propuestas contra enum cerrado de allowed_kinds.
- Modo simulador seguro (sin conexión a actuadores físicos).
"""

from datetime import datetime, timezone
import json
import os
import urllib.error
import urllib.request

MARGEN_RELOJ_S = 2.0


def _parse_iso(fecha_str):
    if not isinstance(fecha_str, str):
        raise ValueError("fecha debe ser string")
    # Manejar sufijo Z como UTC
    if fecha_str.endswith("Z"):
        fecha_str = fecha_str[:-1] + "+00:00"
    dt = datetime.fromisoformat(fecha_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class RobotAdapterD:
    """Adaptador de perfil D con estado local de correlación y deduplicación."""

    def __init__(self, gateway_url=None):
        if gateway_url:
            self.gateway_url = gateway_url.rstrip("/")
        else:
            host = os.environ.get("LFM3_GATEWAY_HOST", "127.0.0.1")
            port = int(os.environ.get("LFM3_GATEWAY_PORT", "8092"))
            self.gateway_url = f"http://{host}:{port}"
        self.vistos = set()
        self.ultimo_observed_at = {}

    def reset(self):
        """Reinicia estado (para tests)."""
        self.vistos.clear()
        self.ultimo_observed_at.clear()

    def evaluar_observacion(self, solicitud, ahora_fn=None):
        """Evalúa una observación sensorial y devuelve propuesta o descarte."""
        ahora = ahora_fn() if ahora_fn else datetime.now(timezone.utc)
        if ahora.tzinfo is None:
            ahora = ahora.replace(tzinfo=timezone.utc)

        # 1. Validación de campos obligatorios
        if not isinstance(solicitud, dict):
            return self._descarte("invalid_schema", None, "solicitud no es un diccionario")
        device_id = solicitud.get("device_id")
        obs_id = solicitud.get("observation_id")
        obs_at_str = solicitud.get("observed_at")
        exp_at_str = solicitud.get("expires_at")
        prompt = solicitud.get("prompt")
        allowed_kinds = solicitud.get("allowed_kinds")

        if not isinstance(device_id, str) or not (1 <= len(device_id) <= 64):
            return self._descarte("invalid_schema", obs_id, "device_id inválido")
        if not isinstance(obs_id, str) or not (1 <= len(obs_id) <= 64):
            return self._descarte("invalid_schema", obs_id, "observation_id inválido")
        if not isinstance(prompt, str) or not (1 <= len(prompt) <= 8000):
            return self._descarte("invalid_schema", obs_id, "prompt inválido")
        if not isinstance(allowed_kinds, list) or not (1 <= len(allowed_kinds) <= 32) \
                or not all(isinstance(k, str) and k for k in allowed_kinds):
            return self._descarte("invalid_schema", obs_id, "allowed_kinds debe ser lista no vacía")

        # 2. Parseo y verificación temporal (reloj y expiración pre-inferencia)
        try:
            dt_obs = _parse_iso(obs_at_str)
            dt_exp = _parse_iso(exp_at_str)
        except Exception as exc:
            return self._descarte("invalid_schema", obs_id, f"error parseando timestamp: {exc}")

        deriva = abs((ahora - dt_obs).total_seconds())
        if deriva > MARGEN_RELOJ_S:
            return self._descarte(
                "drift_clock",
                obs_id,
                f"deriva de reloj ({deriva:.3f}s) supera el margen de {MARGEN_RELOJ_S}s",
            )

        if dt_exp <= dt_obs:
            return self._descarte(
                "expired_pre_inference",
                obs_id,
                "expires_at no es posterior a observed_at",
            )
        if ahora >= dt_exp:
            return self._descarte(
                "expired_pre_inference",
                obs_id,
                "observación ya caducada antes de la inferencia",
            )

        # 3. Deduplicación y secuencia
        if obs_id in self.vistos:
            return self._descarte(
                "duplicate_observation",
                obs_id,
                "observation_id ya fue procesado",
            )
        ultimo_dt = self.ultimo_observed_at.get(device_id)
        if ultimo_dt is not None and dt_obs < ultimo_dt:
            return self._descarte(
                "reordered_observation",
                obs_id,
                "observación recibida fuera de orden temporal",
            )

        # 4. Esquema cerrado para la propuesta del robot
        schema_propuesta = {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": allowed_kinds},
                "payload": {"type": "object", "properties": {
                    "velocidad": {"type": "number"},
                    "angulo": {"type": "number"},
                    "motivo": {"type": "string"},
                }},
            },
            "required": ["kind", "payload"],
        }

        # 5. Construcción de payload hacia el gateway
        mensajes_contenido = []
        img_b64 = solicitud.get("image_base64")
        if img_b64:
            if not isinstance(img_b64, str):
                return self._descarte("invalid_schema", obs_id, "image_base64 debe ser string")
            mime = "image/jpeg" if img_b64.startswith("/9j/") else "image/png"
            mensajes_contenido.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{img_b64}"},
            })
        mensajes_contenido.append({"type": "text", "text": prompt})

        payload_gw = {
            "messages": [{"role": "user", "content": mensajes_contenido}],
            "max_tokens": solicitud.get("max_tokens", 512),
            "temperature": 0.0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "propuesta_robot", "schema": schema_propuesta},
            },
        }

        # 6. Llamada HTTP al gateway
        t_inicio = ahora
        url_completions = f"{self.gateway_url}/v1/chat/completions"
        req_bytes = json.dumps(payload_gw).encode("utf-8")
        req = urllib.request.Request(
            url_completions,
            data=req_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_raw = resp.read()
                cuerpo_gw = json.loads(resp_raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return self._descarte("gateway_error", obs_id, f"gateway respondió HTTP {exc.code}")
        except Exception as exc:
            return self._descarte("gateway_error", obs_id, f"error de red/gateway: {exc}")

        # 7. Verificación post-inferencia (tiempo transcurrido vs expires_at)
        ahora_post = ahora_fn() if ahora_fn else datetime.now(timezone.utc)
        if ahora_post.tzinfo is None:
            ahora_post = ahora_post.replace(tzinfo=timezone.utc)

        if ahora_post >= dt_exp:
            return self._descarte(
                "expired_post_inference",
                obs_id,
                "la inferencia tardó demasiado; la observación caducó antes de emitir respuesta",
            )

        # 8. Verificación de salida completa del modelo
        if not isinstance(cuerpo_gw, dict):
            return self._descarte(
                "invalid_schema", obs_id, "cuerpo del gateway no es un objeto JSON"
            )
        choices = cuerpo_gw.get("choices")
        if not isinstance(choices, list) or not choices:
            return self._descarte("incomplete_output", obs_id, "respuesta sin choices válidos")
        choice = choices[0]
        if not isinstance(choice, dict):
            return self._descarte("incomplete_output", obs_id, "choice inválido")
        finish_reason = choice.get("finish_reason")
        if finish_reason != "stop":
            return self._descarte(
                "incomplete_output",
                obs_id,
                f"finish_reason={finish_reason} (no es 'stop')",
            )

        # 9. Validación de propuesta contra allowed_kinds
        msg_obj = choice.get("message")
        if not isinstance(msg_obj, dict):
            return self._descarte("incomplete_output", obs_id, "message ausente o inválido")
        contenido_txt = msg_obj.get("content", "")
        try:
            propuesta = json.loads(contenido_txt)
        except Exception as exc:
            return self._descarte("invalid_schema", obs_id, f"propuesta no parseable: {exc}")

        if not isinstance(propuesta, dict):
            return self._descarte("invalid_schema", obs_id, "propuesta no es un objeto JSON")
        if not isinstance(propuesta.get("payload"), dict):
            return self._descarte(
                "invalid_schema", obs_id, "payload de propuesta debe ser un objeto"
            )

        kind = propuesta.get("kind")
        if kind not in allowed_kinds:
            return self._descarte(
                "unauthorized_proposal_kind",
                obs_id,
                f"kind '{kind}' fuera de allowed_kinds autorizados",
            )

        # 10. Aceptación segura
        self.vistos.add(obs_id)
        self.ultimo_observed_at[device_id] = dt_obs
        latencia = (ahora_post - t_inicio).total_seconds()
        return {
            "status": "accepted",
            "observation_id": obs_id,
            "device_id": device_id,
            "request_id": cuerpo_gw.get("id", "req-gw"),
            "complete": True,
            "proposal": propuesta,
            "observed_at": obs_at_str,
            "expires_at": exp_at_str,
            "latency_s": round(latencia, 3),
        }

    def _descarte(self, reason, obs_id, detail):
        return {
            "status": "discarded",
            "reason": reason,
            "observation_id": obs_id,
            "detail": detail,
        }
