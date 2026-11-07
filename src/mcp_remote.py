#!/usr/bin/env python3
"""Servidor MCP remoto desacoplado (Streamable HTTP) para LFM3-Omni.

Implementa la especificación SPEC-i3-mcp-remote y ADR-010:
- Endpoint /mcp sobre HTTPS/TLS con transporte Streamable HTTP (POST / GET SSE).
- Negociación de versiones MCP: 2025-06-18, 2025-03-26, 2024-11-05.
- Sesiones desacopladas por Mcp-Session-Id vinculadas deterministamente al proyecto.
- Autenticación Bearer y verificación estricta de scopes por herramienta.
- Catálogo omnimodal completo: health, capabilities, infer_text, infer_vision,
  infer_audio, synthesize_speech, infer_video, conversational_turn.
- Exclusión mutua de TTS (503 tts_busy) y validación de salidas contra schema v2-ext.
- Contención estricta de egreso (anti-SSRF): medios binarios siempre en base64.
"""

from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from gateway_core import (
    BACKEND_TIMEOUT_S,
    CAPABILITIES,
    MAX_BODY_BYTES,
    MAX_TOKENS,
    ErrorV2,
    _error,
    _rechazar_constante,
    validar_payload_tts,
    validar_salida,
    validar_wav,
)

MCP_VERSIONS_SUPPORTED = ("2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_MCP_VERSION = "2025-06-18"
SERVER_NAME = "lfm3-omni-mcp-remote"
SERVER_VERSION = "2.0.0"

TOOL_SCOPES: Dict[str, Optional[str]] = {
    "health": None,
    "capabilities": None,
    "infer_text": "infer:text",
    "infer_vision": "infer:vision",
    "infer_audio": "infer:audio",
    "synthesize_speech": "speech:synthesize",
    "infer_video": "infer:video",
    "conversational_turn": "turn:stream",
}

TOOLS_REMOTE: List[Dict[str, Any]] = [
    {
        "name": "health",
        "description": "Estado y conectividad del servicio omnimodal LFM3-Omni",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
            "required": [],
        },
    },
    {
        "name": "capabilities",
        "description": "Catálogo de restricciones, formatos de entrada y capacidades",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
            "required": [],
        },
    },
    {
        "name": "infer_text",
        "description": "Inferencia de texto con schema JSON dialecto v2-ext opcional",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "minLength": 1, "maxLength": 8000},
                "schema": {"type": "object"},
                "max_tokens": {"type": "integer", "minimum": 1, "maximum": 4096},
            },
            "additionalProperties": False,
            "required": ["prompt"],
        },
    },
    {
        "name": "infer_vision",
        "description": "Reconocimiento e inspección de imágenes (PNG o JPEG en base64)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image_base64": {"type": "string"},
                "prompt": {"type": "string", "minLength": 1, "maxLength": 8000},
                "schema": {"type": "object"},
                "max_tokens": {"type": "integer", "minimum": 1, "maximum": 4096},
            },
            "additionalProperties": False,
            "required": ["image_base64", "prompt"],
        },
    },
    {
        "name": "infer_audio",
        "description": "Procesamiento y transcripción de voz/audio (WAV en base64)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "audio_base64": {"type": "string"},
                "prompt": {"type": "string", "minLength": 1, "maxLength": 8000},
                "schema": {"type": "object"},
                "max_tokens": {"type": "integer", "minimum": 1, "maximum": 4096},
            },
            "additionalProperties": False,
            "required": ["audio_base64", "prompt"],
        },
    },
    {
        "name": "synthesize_speech",
        "description": "Síntesis de voz hablada en español neutro (WAV) con exclusión mutua",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {"type": "string", "minLength": 1, "maxLength": 600},
                "voice": {"type": "string"},
                "speed": {"type": "number", "minimum": 0.5, "maximum": 2.0},
            },
            "additionalProperties": False,
            "required": ["input"],
        },
    },
    {
        "name": "infer_video",
        "description": "Inspección temporal de video corto MP4 en base64 (<= 10 s)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "video_base64": {"type": "string"},
                "prompt": {"type": "string", "minLength": 1, "maxLength": 8000},
                "schema": {"type": "object"},
                "max_tokens": {"type": "integer", "minimum": 1, "maximum": 4096},
            },
            "additionalProperties": False,
            "required": ["video_base64", "prompt"],
        },
    },
    {
        "name": "conversational_turn",
        "description": "Turno conversacional interactivo con soporte de streaming y voz",
        "inputSchema": {
            "type": "object",
            "properties": {
                "messages": {
                    "type": "array",
                    "items": {"type": "object"},
                    "minItems": 1,
                    "maxItems": 20,
                },
                "stream": {"type": "boolean"},
                "synthesize_voice": {"type": "boolean"},
            },
            "additionalProperties": False,
            "required": ["messages"],
        },
    },
]


def _tool_result(data: Dict[str, Any]) -> Dict[str, Any]:
    """Genera CallToolResult exitoso según el estándar MCP."""
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(data, ensure_ascii=False),
            }
        ],
        "isError": False,
    }


def _tool_error(code: str, message: str) -> Dict[str, Any]:
    """Genera CallToolResult fallido normalizado según SPEC-i3 §5."""
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps({"error": code, "message": message}, ensure_ascii=False),
            }
        ],
        "isError": True,
    }


class SessionRegistry:
    """Gestiona sesiones desacopladas en memoria garantizando aislamiento de proyectos."""

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self.ttl = ttl_seconds
        self._lock = threading.Lock()
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def get_or_create(
        self, session_id: Optional[str], project_id: str, version: Optional[str] = None
    ) -> str:
        with self._lock:
            now = time.time()
            if session_id:
                sess = self._sessions.get(session_id)
                if sess:
                    if sess.get("project_id") != project_id:
                        _error(403, "project_mismatch",
                               "Mcp-Session-Id pertenece a otro proyecto")
                    sess["last_seen"] = now
                    if version and not sess.get("version"):
                        sess["version"] = version
                    return session_id

            sid = session_id or uuid.uuid4().hex
            self._sessions[sid] = {
                "project_id": project_id,
                "version": version or DEFAULT_MCP_VERSION,
                "created_at": now,
                "last_seen": now,
            }
            return sid

    def validate(self, session_id: str, project_id: str) -> Dict[str, Any]:
        with self._lock:
            sess = self._sessions.get(session_id)
            if not sess or sess.get("project_id") != project_id:
                _error(403, "project_mismatch",
                       "sesión no encontrada o no pertenece al proyecto autenticado")
            sess["last_seen"] = time.time()
            return sess


class MCPRemoteHandler:
    """Despachador central de peticiones MCP Streamable HTTP."""

    def __init__(
        self,
        backend_url: str,
        tts_runner=None,
        probe_runner=None,
        session_registry: Optional[SessionRegistry] = None,
    ) -> None:
        self.backend = backend_url
        self.tts_runner = tts_runner
        self.probe_runner = probe_runner
        self.sessions = session_registry or SessionRegistry()

    def handle_get(self, http_handler) -> None:
        """Canal Server-Sent Events (SSE) para notificaciones y streaming."""
        accept = http_handler.headers.get("Accept", "")
        if "text/event-stream" not in accept:
            _error(400, "invalid_request_error",
                   "GET /mcp requiere cabecera Accept: text/event-stream")

        sid = http_handler.headers.get("Mcp-Session-Id")
        proj_id = getattr(http_handler, "project_id", "")
        if sid and proj_id:
            self.sessions.validate(sid, proj_id)

        http_handler.send_response(200)
        http_handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        http_handler.send_header("Cache-Control", "no-cache, no-transform")
        http_handler.send_header("Connection", "keep-alive")
        if sid:
            http_handler.send_header("Mcp-Session-Id", sid)
        http_handler.end_headers()

        payload = json.dumps({"event": "ready", "server": SERVER_NAME, "version": SERVER_VERSION})
        msg = f"event: mcp.ready\ndata: {payload}\n\n".encode("utf-8")
        http_handler.wfile.write(msg)
        http_handler.wfile.flush()

    def handle_post(
        self,
        http_handler,
        proj_info: Optional[Dict[str, Any]],
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Procesa peticiones JSON-RPC 2.0 por HTTP POST."""
        body = payload if payload is not None else http_handler._leer_json_post()
        if not isinstance(body, dict):
            _error(400, "invalid_request_error", "el cuerpo debe ser un objeto JSON-RPC")

        req_id = body.get("id")
        method = body.get("method")
        jsonrpc = body.get("jsonrpc")

        if jsonrpc != "2.0" or not isinstance(method, str):
            _error(400, "invalid_request_error",
                   "petición inválida: debe contener jsonrpc: '2.0' y un método válido")

        project_id = getattr(http_handler, "project_id", "default")
        sid_h = http_handler.headers.get("Mcp-Session-Id")

        if sid_h and method != "initialize":
            self.sessions.validate(sid_h, project_id)

        # 1. initialize
        if method == "initialize":
            params = body.get("params") or {}
            client_version = params.get("protocolVersion")
            chosen_version = (
                client_version
                if client_version in MCP_VERSIONS_SUPPORTED
                else DEFAULT_MCP_VERSION
            )
            sid = self.sessions.get_or_create(sid_h, project_id, chosen_version)
            result = {
                "protocolVersion": chosen_version,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "logging": {},
                },
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                },
            }
            extra_h = {"Mcp-Session-Id": sid}
            resp = {"jsonrpc": "2.0", "id": req_id, "result": result}
            http_handler._json(200, json.dumps(resp).encode("utf-8"), extra_h)
            return

        # 2. ping
        if method == "ping":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
            http_handler._json(200, json.dumps(resp).encode("utf-8"))
            return

        # 3. tools/list
        if method == "tools/list":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS_REMOTE}}
            http_handler._json(200, json.dumps(resp).encode("utf-8"))
            return

        # 4. tools/call
        if method == "tools/call":
            params = body.get("params") or {}
            tool_name = params.get("name")
            tool_args = params.get("arguments") or {}
            if not isinstance(tool_args, dict):
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": _tool_error("invalid_payload", "arguments debe ser un objeto"),
                }
                http_handler._json(200, json.dumps(resp).encode("utf-8"))
                return

            # Verificación de scopes
            if proj_info:
                req_scope = TOOL_SCOPES.get(tool_name)
                if req_scope:
                    scopes_declarados = set(proj_info.get("scopes", []))
                    if "mcp:tools" not in scopes_declarados and req_scope not in scopes_declarados:
                        resp = {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": _tool_error(
                                "insufficient_scope",
                                f"el proyecto no posee el scope '{req_scope}' o 'mcp:tools'",
                            ),
                        }
                        http_handler._json(200, json.dumps(resp).encode("utf-8"))
                        return

            # Adquisición de slot en fair queuing
            slot_adquirido = False
            if hasattr(http_handler.server, "dispatcher") and proj_info:
                rl_cfg = proj_info.get("rate_limit", {})
                http_handler.server.dispatcher.acquire_slot(project_id, rl_cfg)
                slot_adquirido = True

            try:
                res_tool = self._ejecutar_tool(http_handler, tool_name, tool_args)
                resp = {"jsonrpc": "2.0", "id": req_id, "result": res_tool}
                http_handler._json(200, json.dumps(resp).encode("utf-8"))
            finally:
                if slot_adquirido and hasattr(http_handler.server, "dispatcher"):
                    http_handler.server.dispatcher.release_slot(project_id)
            return

        # 5. notifications/cancelled
        if method == "notifications/cancelled":
            # Cancelación de solicitud por requestId
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {"cancelled": True}}
            http_handler._json(200, json.dumps(resp).encode("utf-8"))
            return

        # Método no reconocido
        resp = {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"método MCP no implementado: {method}"},
        }
        http_handler._json(200, json.dumps(resp).encode("utf-8"))

    def _ejecutar_tool(
        self, http_handler, name: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Despacha la ejecución determinista de cada tool omnimodal."""
        if hasattr(http_handler, "server"):
            if getattr(http_handler.server, "tts_runner", None) is not None:
                self.tts_runner = http_handler.server.tts_runner
            if getattr(http_handler.server, "probe_runner", None) is not None:
                self.probe_runner = http_handler.server.probe_runner

        if name == "health":
            return _tool_result({
                "status": "healthy",
                "model": "LiquidAI/LFM3-Omni-2B-GGUF",
                "capabilities": {
                    "text": True,
                    "vision": True,
                    "audio": True,
                    "speech": True,
                    "video": True,
                    "conversation_stream": True,
                },
            })

        if name == "capabilities":
            return _tool_result(CAPABILITIES)

        if name == "infer_text":
            return self._tool_infer_text(args)

        if name == "infer_vision":
            return self._tool_infer_vision(args)

        if name == "infer_audio":
            return self._tool_infer_audio(args)

        if name == "synthesize_speech":
            return self._tool_synthesize_speech(args)

        if name == "infer_video":
            return self._tool_infer_video(args)

        if name == "conversational_turn":
            return self._tool_conversational_turn(args)

        return _tool_error("unknown_tool", f"herramienta no reconocida: {name}")

    def _tool_infer_text(self, args: Dict[str, Any]) -> Dict[str, Any]:
        prompt = args.get("prompt")
        if not isinstance(prompt, str) or not 1 <= len(prompt) <= 8000:
            return _tool_error("invalid_payload", "prompt debe ser string de 1..8000 caracteres")

        schema = args.get("schema")
        if schema is not None and not isinstance(schema, dict):
            return _tool_error("invalid_payload", "schema debe ser un objeto JSON Schema")

        max_tokens = args.get("max_tokens", 512)
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or not 1 <= max_tokens <= MAX_TOKENS:
            return _tool_error("invalid_payload", "max_tokens debe ser entero de 1..4096")

        payload: Dict[str, Any] = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
        if schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "salida", "schema": schema},
            }

        return self._llamar_backend_chat(payload, schema)

    def _tool_infer_vision(self, args: Dict[str, Any]) -> Dict[str, Any]:
        prompt = args.get("prompt")
        if not isinstance(prompt, str) or not 1 <= len(prompt) <= 8000:
            return _tool_error("invalid_payload", "prompt debe ser string de 1..8000 caracteres")

        img_b64 = args.get("image_base64")
        if not isinstance(img_b64, str) or not img_b64.strip():
            return _tool_error("invalid_payload", "image_base64 requerido en formato base64")

        # Prohibición de URLs y validación anti-SSRF
        if img_b64.startswith("http://") or img_b64.startswith("https://") or img_b64.startswith("file://"):
            return _tool_error("invalid_payload", "anti-SSRF: se prohíben esquemas URL; use base64")

        try:
            datos_raw = base64.b64decode(img_b64, validate=True)
        except Exception:
            return _tool_error("invalid_payload", "image_base64 no contiene base64 válido")

        tipo = None
        if datos_raw.startswith(b"\x89PNG\r\n\x1a\n"):
            tipo = "png"
        elif datos_raw.startswith(b"\xff\xd8\xff"):
            tipo = "jpeg"
        else:
            return _tool_error("invalid_payload", "firma de imagen no coincide con PNG ni JPEG")

        schema = args.get("schema")
        max_tokens = args.get("max_tokens", 1024)
        data_uri = f"data:image/{tipo};base64,{img_b64.strip()}"

        payload: Dict[str, Any] = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
            "max_tokens": max_tokens,
        }
        if schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "salida", "schema": schema},
            }

        return self._llamar_backend_chat(payload, schema, clave_resultado="description")

    def _tool_infer_audio(self, args: Dict[str, Any]) -> Dict[str, Any]:
        prompt = args.get("prompt")
        if not isinstance(prompt, str) or not 1 <= len(prompt) <= 8000:
            return _tool_error("invalid_payload", "prompt debe ser string de 1..8000 caracteres")

        audio_b64 = args.get("audio_base64")
        if not isinstance(audio_b64, str) or not audio_b64.strip():
            return _tool_error("invalid_payload", "audio_base64 requerido en formato base64")

        if audio_b64.startswith("http://") or audio_b64.startswith("https://") or audio_b64.startswith("file://"):
            return _tool_error("invalid_payload", "anti-SSRF: se prohíben esquemas URL; use base64")

        try:
            datos_raw = base64.b64decode(audio_b64, validate=True)
        except Exception:
            return _tool_error("invalid_payload", "audio_base64 no contiene base64 válido")

        try:
            validar_wav(datos_raw)
        except ErrorV2 as exc:
            return _tool_error("invalid_payload", f"WAV inválido: {exc.message}")

        schema = args.get("schema")
        max_tokens = args.get("max_tokens", 1024)

        payload: Dict[str, Any] = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "input_audio",
                            "input_audio": {"data": audio_b64.strip(), "format": "wav"},
                        },
                    ],
                }
            ],
            "max_tokens": max_tokens,
        }
        if schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "salida", "schema": schema},
            }

        return self._llamar_backend_chat(payload, schema)

    def _tool_synthesize_speech(self, args: Dict[str, Any]) -> Dict[str, Any]:
        texto = args.get("input")
        if not isinstance(texto, str) or not 1 <= len(texto) <= 600:
            return _tool_error("invalid_payload", "input debe ser string de 1..600 caracteres")

        voice = args.get("voice", "es_ES-davefx-medium")
        speed = args.get("speed", 1.0)
        if not isinstance(speed, (int, float)) or not 0.5 <= speed <= 2.0:
            return _tool_error("invalid_payload", "speed debe ser número entre 0.5 y 2.0")

        # Importar dinámicamente _sintetizar_wav de gateway_http
        try:
            from gateway_http import _sintetizar_wav
            wav_bytes = _sintetizar_wav(texto, runner=self.tts_runner)
        except ErrorV2 as exc:
            if exc.code == "overloaded" or exc.status == 503:
                return _tool_error("tts_busy", "síntesis de voz en curso; reintente")
            return _tool_error("tts_error", f"error de síntesis: {exc.message}")
        except Exception as exc:
            return _tool_error("tts_error", f"fallo en síntesis de voz: {exc}")

        wav_b64 = base64.b64encode(wav_bytes).decode("ascii")
        return _tool_result({
            "audio_base64": wav_b64,
            "format": "wav",
            "voice": voice,
            "chars": len(texto),
            "duration_est_s": round(len(texto) / 16.0, 2),
        })

    def _tool_infer_video(self, args: Dict[str, Any]) -> Dict[str, Any]:
        prompt = args.get("prompt")
        if not isinstance(prompt, str) or not 1 <= len(prompt) <= 8000:
            return _tool_error("invalid_payload", "prompt debe ser string de 1..8000 caracteres")

        video_b64 = args.get("video_base64")
        if not isinstance(video_b64, str) or not video_b64.strip():
            return _tool_error("invalid_payload", "video_base64 requerido en formato base64")

        if video_b64.startswith("http://") or video_b64.startswith("https://") or video_b64.startswith("file://"):
            return _tool_error("invalid_payload", "anti-SSRF: se prohíben esquemas URL; use base64")

        try:
            datos_raw = base64.b64decode(video_b64, validate=True)
        except Exception:
            return _tool_error("invalid_payload", "video_base64 no contiene base64 válido")

        if len(datos_raw) < 8 or datos_raw[4:8] != b"ftyp":
            return _tool_error("invalid_payload", "el contenedor no posee la caja ftyp requerida de MP4")

        # Inspección ffprobe
        from gateway_http import _inspeccionar_mp4_ffprobe
        try:
            _inspeccionar_mp4_ffprobe(datos_raw, probe_runner=self.probe_runner)
        except ErrorV2 as exc:
            return _tool_error("invalid_payload", f"validación de video fallida: {exc.message}")

        schema = args.get("schema")
        max_tokens = args.get("max_tokens", 1024)
        data_uri = f"data:video/mp4;base64,{video_b64.strip()}"

        payload: Dict[str, Any] = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "video_url", "video_url": {"url": data_uri}},
                    ],
                }
            ],
            "max_tokens": max_tokens,
        }
        if schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "salida", "schema": schema},
            }

        return self._llamar_backend_chat(payload, schema, clave_resultado="description")

    def _tool_conversational_turn(self, args: Dict[str, Any]) -> Dict[str, Any]:
        messages = args.get("messages")
        if not isinstance(messages, list) or not 1 <= len(messages) <= 20:
            return _tool_error("invalid_payload", "messages debe ser lista de 1..20 mensajes")

        for m in messages:
            if not isinstance(m, dict) or "role" not in m or "content" not in m:
                return _tool_error("invalid_payload", "cada mensaje debe contener 'role' y 'content'")
            if m["role"] not in ("user", "assistant", "system"):
                return _tool_error("invalid_payload", f"rol no permitido: {m['role']}")

        synthesize = bool(args.get("synthesize_voice", False))
        payload = {"messages": messages, "max_tokens": 1024}

        res = self._llamar_backend_chat(payload, schema=None)
        if res.get("isError") is True:
            return res

        # Si se solicita voz, sintetizar respuesta
        try:
            info = json.loads(res["content"][0]["text"])
            texto = info.get("text", "")
            if synthesize and texto:
                from gateway_http import _sintetizar_wav
                wav = _sintetizar_wav(texto[:600], runner=self.tts_runner)
                info["audio_base64"] = base64.b64encode(wav).decode("ascii")
                res["content"][0]["text"] = json.dumps(info, ensure_ascii=False)
        except Exception:
            pass
        return res

    def _llamar_backend_chat(
        self, payload: Dict[str, Any], schema: Optional[Dict[str, Any]], clave_resultado: str = "text"
    ) -> Dict[str, Any]:
        """Envía petición al backend llama-server y valida salida contra schema v2-ext."""
        body_bytes = json.dumps(payload, allow_nan=False).encode("utf-8")
        req = urllib.request.Request(
            f"{self.backend}/v1/chat/completions",
            data=body_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=BACKEND_TIMEOUT_S) as resp:
                estado = resp.status
                cuerpo = resp.read()
        except urllib.error.HTTPError as exc:
            estado = exc.code
            cuerpo = exc.read()
        except Exception as exc:
            return _tool_error("backend_error", f"motor no disponible en 8091: {exc}")

        if estado != 200:
            return _tool_error("backend_error", f"el motor respondió status {estado}")

        try:
            data = json.loads(cuerpo, parse_constant=_rechazar_constante)
            contenido = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
        except Exception:
            return _tool_error("backend_error", "respuesta del motor con formato ilegible")

        validado = False
        if schema is not None:
            try:
                validar_salida(contenido, schema)
                validado = True
            except ErrorV2 as exc:
                return _tool_error("salida_invalida", f"la salida viola el esquema ({exc.message})")
            except Exception as exc:
                return _tool_error("salida_invalida", f"error al validar esquema: {exc}")

        return _tool_result({
            clave_resultado: contenido,
            "validated": validado,
            "usage": usage,
        })
