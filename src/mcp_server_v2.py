#!/usr/bin/env python3
"""Servidor MCP stdio v2 para LFM3-Omni.

Contrato: docs/contracts/mcp-tools-v2.md · SPEC: docs/specs/SPEC-i1-vm-mcp-v2.md
Transporte stdio (ADR-002, ADR-008); delega en el gateway HTTP loopback
(127.0.0.1:8092) y reutiliza gateway_core para prevalidación y frontera de
salida. Comparte con los clientes HTTP el cerrojo de exclusión mutua de TTS
(ADR-007, 503 sin cola) y los límites de seguridad.
Preserva intacto src/mcp_server.py (mcp-tools-v1).
"""

import base64
import binascii
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Añadir src al path para importar gateway_core
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gateway_core import (  # noqa: E402
    ErrorV2,
    MAX_TTS_CHARS,
    MAX_TOKENS,
    validar_schema,
    validar_salida,
    validar_png,
    validar_jpeg,
    validar_wav,
    validar_mp4_bytes,
    validar_payload_tts,
)

PROTO_DEFAULT = "2025-06-18"
PROTO_SOPORTADAS = ("2025-06-18", "2025-03-26")
GATEWAY_HOST = os.environ.get("LFM3_GATEWAY_HOST", "127.0.0.1")
GATEWAY_PORT = int(os.environ.get("LFM3_GATEWAY_PORT", "8092"))
GATEWAY_URL = f"http://{GATEWAY_HOST}:{GATEWAY_PORT}"
MODELO = "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M"
INICIALIZADO = False

TOOLS = [
    {
        "name": "health",
        "description": "Estado y capacidades del servicio omnimodal LFM3-Omni",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
            "required": [],
        },
    },
    {
        "name": "infer_text",
        "description": "Inferencia de texto con esquema dialecto v2-ext opcional",
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
        "description": "Inferencia sobre imagen (PNG o JPEG en base64)",
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
        "description": "Inferencia y ASR sobre audio (WAV en base64)",
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
        "description": "Síntesis de voz en español con cerrojo de exclusión mutua",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {"type": "string", "minLength": 1, "maxLength": 600},
                "voice": {"type": "string"},
                "speed": {"type": "number", "minimum": 0.5, "maximum": 2.0},
                "response_format": {"type": "string", "enum": ["wav"]},
            },
            "additionalProperties": False,
            "required": ["input"],
        },
    },
    {
        "name": "infer_video",
        "description": "Inferencia sobre video corto MP4 (base64, <= 10s, 120f)",
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
]


def respond(msg_id, result=None, error=None):
    body = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        body["error"] = error
    else:
        body["result"] = result
    return json.dumps(body, ensure_ascii=False)


def _tool_result(data):
    return {
        "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
        "isError": False,
    }


def _tool_error(message):
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _http_gateway(method, path, payload=None, timeout=120, raw_response=False):
    """Llamada HTTP al gateway loopback. Devuelve (status, cuerpo)."""
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(f"{GATEWAY_URL}{path}", data=data, headers=headers,
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if raw_response:
                return resp.status, raw
            return resp.status, json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw_err = exc.read()
        if raw_response and exc.code == 503:
            return 503, raw_err
        try:
            cuerpo = json.loads(raw_err.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            cuerpo = {"error": {"message": str(exc)}}
        return exc.code, cuerpo
    except (urllib.error.URLError, OSError) as exc:
        raise ConnectionError(f"gateway no disponible en {GATEWAY_URL}: {exc}")


def _extraer_texto_y_usage(cuerpo):
    """Extrae (contenido, usage) de la respuesta chat.completions del gateway."""
    choices = cuerpo.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("respuesta sin choices utilizables")
    mensaje = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(mensaje, dict):
        raise ValueError("respuesta sin message utilizable")
    contenido = mensaje.get("content")
    if not isinstance(contenido, str):
        raise ValueError("content de la respuesta no es string")
    usage = cuerpo.get("usage")
    if not isinstance(usage, dict):
        raise ValueError("usage ausente o no es objeto")
    return contenido, usage


def handle_initialize(msg):
    global INICIALIZADO
    pedido = (msg.get("params") or {}).get("protocolVersion", PROTO_DEFAULT)
    version = pedido if pedido in PROTO_SOPORTADAS else PROTO_DEFAULT
    INICIALIZADO = True
    return {
        "protocolVersion": version,
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "lfm3-omni-mcp-v2", "version": "0.2.0"},
    }


def _exige_sesion():
    if not INICIALIZADO:
        return {"code": -32002, "message": "initialize requerido como primer método"}
    return None


def handle_tools_list(_msg):
    return {"tools": TOOLS}


def _campos_extra(args, declarados):
    extra = sorted(set(args) - declarados)
    if extra:
        return f"arguments inválidos: campos no declarados en el contrato: {extra}"
    return None


def _validar_prompt(valor, campo="prompt"):
    if not isinstance(valor, str) or not 1 <= len(valor) <= 8000:
        return f"arguments inválidos: {campo} debe ser string de 1..8000 caracteres"
    return None


def _validar_max_tokens(args, default=512):
    max_tokens = args.get("max_tokens", default)
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) \
            or not 1 <= max_tokens <= MAX_TOKENS:
        return None, "arguments inválidos: max_tokens debe ser entero 1..4096"
    return max_tokens, None


def _validar_schema_arg(args):
    schema = args.get("schema")
    if "schema" in args and not isinstance(schema, dict):
        return None, "arguments inválidos: schema debe ser un objeto JSON Schema"
    if schema is not None:
        try:
            validar_schema(schema)
        except ErrorV2 as exc:
            return None, f"arguments inválidos: {exc.message}"
        except Exception as exc:
            return None, f"arguments inválidos en schema: {exc}"
    return schema, None


def handle_health(msg):
    args = (msg.get("params") or {}).get("arguments")
    if args not in (None, {}):
        return _tool_error("arguments inválidos: health no acepta campos")
    try:
        status, cuerpo_h = _http_gateway("GET", "/healthz", timeout=5)
        if status != 200 or not isinstance(cuerpo_h, dict) \
                or cuerpo_h.get("status") != "ok":
            return _tool_result({
                "state": "down",
                "model": MODELO,
                "gateway_port": GATEWAY_PORT,
                "backend_port": 8091,
                "capabilities": {},
            })
        _, cuerpo_c = _http_gateway("GET", "/v1/capabilities", timeout=5)
        return _tool_result({
            "state": "up",
            "model": MODELO,
            "gateway_port": GATEWAY_PORT,
            "backend_port": 8091,
            "capabilities": cuerpo_c,
        })
    except (ConnectionError, Exception):
        return _tool_result({
            "state": "down",
            "model": MODELO,
            "gateway_port": GATEWAY_PORT,
            "backend_port": 8091,
            "capabilities": {},
        })


def _delegar_chat(payload, schema):
    """Envía POST /v1/chat/completions al gateway y valida salida del modelo."""
    try:
        status, cuerpo = _http_gateway("POST", "/v1/chat/completions", payload)
    except ConnectionError as exc:
        return _tool_error(str(exc))
    except Exception as exc:
        return _tool_error(f"error en llamada al gateway: {exc}")

    if status != 200:
        err = cuerpo.get("error") if isinstance(cuerpo, dict) else {}
        detalle = err.get("message") if isinstance(err, dict) else str(cuerpo)
        return _tool_error(f"gateway respondió {status}: {detalle}")

    try:
        contenido, usage = _extraer_texto_y_usage(cuerpo)
    except ValueError as exc:
        return _tool_error(f"salida_invalida: {exc}")

    if schema is not None:
        try:
            validar_salida(contenido, schema)
        except ErrorV2 as exc:
            return _tool_error(f"salida_invalida: la salida viola el esquema ({exc.message})")
        except Exception as exc:
            return _tool_error(f"salida_invalida: {exc}")
        return None, contenido, True, usage
    return None, contenido, False, usage


def handle_infer_text(msg):
    args = (msg.get("params") or {}).get("arguments")
    if not isinstance(args, dict):
        return _tool_error("arguments inválidos: debe ser un objeto")
    fallo = _campos_extra(args, {"prompt", "schema", "max_tokens"})
    if fallo:
        return _tool_error(fallo)
    fallo = _validar_prompt(args.get("prompt"), "prompt")
    if fallo:
        return _tool_error(fallo)
    max_tokens, fallo = _validar_max_tokens(args, default=512)
    if fallo:
        return _tool_error(fallo)
    schema, fallo = _validar_schema_arg(args)
    if fallo:
        return _tool_error(fallo)

    payload = {
        "messages": [{"role": "user", "content": args["prompt"]}],
        "max_tokens": max_tokens,
    }
    if schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "salida", "schema": schema},
        }

    res = _delegar_chat(payload, schema)
    if isinstance(res, dict):
        return res
    _, contenido, validado, usage = res
    return _tool_result({"text": contenido, "validated": validado, "usage": usage})


def handle_infer_vision(msg):
    args = (msg.get("params") or {}).get("arguments")
    if not isinstance(args, dict):
        return _tool_error("arguments inválidos: debe ser un objeto")
    fallo = _campos_extra(args, {"image_base64", "prompt", "schema", "max_tokens"})
    if fallo:
        return _tool_error(fallo)
    fallo = _validar_prompt(args.get("prompt"), "prompt")
    if fallo:
        return _tool_error(fallo)
    imagen_b64 = args.get("image_base64")
    if not isinstance(imagen_b64, str) or not imagen_b64:
        return _tool_error("arguments inválidos: image_base64 es obligatorio (string no vacío)")
    try:
        raw = base64.b64decode(imagen_b64, validate=True)
    except (binascii.Error, ValueError):
        return _tool_error("arguments inválidos: image_base64 no decodifica como base64")

    # Validación mágica de frontera con gateway_core
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
        try:
            validar_png(raw)
        except ErrorV2 as exc:
            return _tool_error(f"arguments inválidos: {exc.message}")
    elif raw.startswith(b"\xff\xd8"):
        mime = "image/jpeg"
        try:
            validar_jpeg(raw)
        except ErrorV2 as exc:
            return _tool_error(f"arguments inválidos: {exc.message}")
    else:
        return _tool_error("arguments inválidos: formato no soportado, se requiere PNG o JPEG")

    max_tokens, fallo = _validar_max_tokens(args, default=1024)
    if fallo:
        return _tool_error(fallo)
    schema, fallo = _validar_schema_arg(args)
    if fallo:
        return _tool_error(fallo)

    payload = {
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{imagen_b64}"}},
            {"type": "text", "text": args["prompt"]},
        ]}],
        "max_tokens": max_tokens,
    }
    if schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "salida", "schema": schema},
        }

    res = _delegar_chat(payload, schema)
    if isinstance(res, dict):
        return res
    _, contenido, validado, usage = res
    return _tool_result({"description": contenido, "validated": validado, "usage": usage})


def handle_infer_audio(msg):
    args = (msg.get("params") or {}).get("arguments")
    if not isinstance(args, dict):
        return _tool_error("arguments inválidos: debe ser un objeto")
    fallo = _campos_extra(args, {"audio_base64", "prompt", "schema", "max_tokens"})
    if fallo:
        return _tool_error(fallo)
    fallo = _validar_prompt(args.get("prompt"), "prompt")
    if fallo:
        return _tool_error(fallo)
    audio_b64 = args.get("audio_base64")
    if not isinstance(audio_b64, str) or not audio_b64:
        return _tool_error("arguments inválidos: audio_base64 es obligatorio (string no vacío)")
    try:
        raw = base64.b64decode(audio_b64, validate=True)
    except (binascii.Error, ValueError):
        return _tool_error("arguments inválidos: audio_base64 no decodifica como base64")

    # Detección de formato y validación con gateway_core
    if raw.startswith(b"RIFF") and len(raw) >= 12 and raw[8:12] == b"WAVE":
        fmt = "wav"
        try:
            validar_wav(raw)
        except ErrorV2 as exc:
            return _tool_error(f"arguments inválidos: {exc.message}")
    else:
        return _tool_error("arguments inválidos: formato no soportado, se requiere WAV")

    max_tokens, fallo = _validar_max_tokens(args, default=1024)
    if fallo:
        return _tool_error(fallo)
    schema, fallo = _validar_schema_arg(args)
    if fallo:
        return _tool_error(fallo)

    payload = {
        "messages": [{"role": "user", "content": [
            {"type": "input_audio", "input_audio": {"data": audio_b64, "format": fmt}},
            {"type": "text", "text": args["prompt"]},
        ]}],
        "max_tokens": max_tokens,
    }
    if schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "salida", "schema": schema},
        }

    res = _delegar_chat(payload, schema)
    if isinstance(res, dict):
        return res
    _, contenido, validado, usage = res
    return _tool_result({"text": contenido, "validated": validado, "usage": usage})


def handle_synthesize_speech(msg):
    args = (msg.get("params") or {}).get("arguments")
    if not isinstance(args, dict):
        return _tool_error("arguments inválidos: debe ser un objeto")
    fallo = _campos_extra(args, {"input", "voice", "speed", "response_format"})
    if fallo:
        return _tool_error(fallo)
    resp_fmt = args.get("response_format", "wav")
    if resp_fmt != "wav":
        return _tool_error("arguments inválidos: response_format sólo admite 'wav'")
    texto = args.get("input")
    if not isinstance(texto, str) or not 1 <= len(texto) <= MAX_TTS_CHARS:
        return _tool_error(
            f"arguments inválidos: input debe ser string de 1..{MAX_TTS_CHARS} caracteres"
        )
    # Prevalidación de TTS payload con gateway_core
    try:
        validar_payload_tts({"input": texto, "language": "es", "response_format": "wav"})
    except ErrorV2 as exc:
        return _tool_error(f"arguments inválidos: {exc.message}")

    voice = args.get("voice", "es_ES-davefx-medium")
    if not isinstance(voice, str):
        return _tool_error("arguments inválidos: voice debe ser string")
    speed = args.get("speed", 1.0)
    if not isinstance(speed, (int, float)) or isinstance(speed, bool) \
            or not 0.5 <= speed <= 2.0:
        return _tool_error("arguments inválidos: speed debe ser número entre 0.5 y 2.0")

    payload = {
        "input": texto,
        "language": "es",
        "response_format": "wav",
    }
    try:
        status, respuesta = _http_gateway(
            "POST", "/v1/audio/speech", payload, timeout=60, raw_response=True
        )
    except ConnectionError as exc:
        return _tool_error(str(exc))
    except Exception as exc:
        return _tool_error(f"error en síntesis de voz: {exc}")

    if status == 503:
        return _tool_error("tts_busy: motor de voz ocupado (503 reintentable)")
    if status != 200:
        try:
            err = json.loads(respuesta.decode("utf-8"))
            detalle = err.get("error", {}).get("message", str(status))
        except Exception:
            detalle = str(status)
        return _tool_error(f"gateway respondió {status}: {detalle}")

    audio_b64 = base64.b64encode(respuesta).decode("ascii")
    duracion_est = round(len(texto) / 15.0, 2)
    return _tool_result({
        "audio_base64": audio_b64,
        "format": "wav",
        "voice": voice,
        "chars": len(texto),
        "duration_est_s": duracion_est,
    })


def handle_infer_video(msg):
    args = (msg.get("params") or {}).get("arguments")
    if not isinstance(args, dict):
        return _tool_error("arguments inválidos: debe ser un objeto")
    fallo = _campos_extra(args, {"video_base64", "prompt", "schema", "max_tokens"})
    if fallo:
        return _tool_error(fallo)
    fallo = _validar_prompt(args.get("prompt"), "prompt")
    if fallo:
        return _tool_error(fallo)
    video_b64 = args.get("video_base64")
    if not isinstance(video_b64, str) or not video_b64:
        return _tool_error("arguments inválidos: video_base64 es obligatorio (string no vacío)")
    try:
        raw = base64.b64decode(video_b64, validate=True)
    except (binascii.Error, ValueError):
        return _tool_error("arguments inválidos: video_base64 no decodifica como base64")

    try:
        validar_mp4_bytes(raw)
    except ErrorV2 as exc:
        return _tool_error(f"arguments inválidos: {exc.message}")

    max_tokens, fallo = _validar_max_tokens(args, default=1024)
    if fallo:
        return _tool_error(fallo)
    schema, fallo = _validar_schema_arg(args)
    if fallo:
        return _tool_error(fallo)

    payload = {
        "messages": [{"role": "user", "content": [
            {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{video_b64}"}},
            {"type": "text", "text": args["prompt"]},
        ]}],
        "max_tokens": max_tokens,
    }
    if schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "salida", "schema": schema},
        }

    res = _delegar_chat(payload, schema)
    if isinstance(res, dict):
        return res
    _, contenido, validado, usage = res
    return _tool_result({"description": contenido, "validated": validado, "usage": usage})


TOOLS_HANDLERS = {
    "health": handle_health,
    "infer_text": handle_infer_text,
    "infer_vision": handle_infer_vision,
    "infer_audio": handle_infer_audio,
    "synthesize_speech": handle_synthesize_speech,
    "infer_video": handle_infer_video,
}


def handle_tools_call(msg):
    nombre = (msg.get("params") or {}).get("name")
    handler = TOOLS_HANDLERS.get(nombre)
    if handler is None:
        return {"error": {"code": -32602, "message": f"tool no conocida: {nombre}"}}
    return handler(msg)


DESPACHO = {
    "initialize": handle_initialize,
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
    "notifications/initialized": lambda _msg: None,
}


def procesar(linea):
    try:
        msg = json.loads(linea)
    except json.JSONDecodeError as exc:
        return respond(None, error={"code": -32700, "message": f"parse error: {exc}"})
    if not isinstance(msg, dict):
        return respond(None, error={
            "code": -32600, "message": "el mensaje debe ser un objeto JSON"})
    if "id" not in msg:
        return None  # notificación JSON-RPC
    metodo = msg.get("method", "")
    handler = DESPACHO.get(metodo)
    if handler is None:
        return respond(
            msg.get("id"),
            error={"code": -32601, "message": f"método no conocido: {metodo}"},
        )
    if metodo != "initialize":
        sesion = _exige_sesion()
        if sesion is not None:
            return respond(msg.get("id"), error=sesion)
    params = msg.get("params")
    if params is not None and not isinstance(params, dict):
        return respond(msg.get("id"), error={
            "code": -32600, "message": "params debe ser un objeto"})
    try:
        resultado = handler(msg)
    except RecursionError:
        return respond(msg.get("id"), error={
            "code": -32603, "message": "error interno: profundidad excesiva"})
    except Exception as exc:
        return respond(msg.get("id"), error={
            "code": -32603, "message": f"error interno: {exc}"})
    if isinstance(resultado, dict) and "error" in resultado:
        return respond(msg.get("id"), error=resultado["error"])
    return respond(msg.get("id"), result=resultado)


def main():
    for linea in sys.stdin:
        linea = linea.strip()
        if not linea:
            continue
        respuesta = procesar(linea)
        if respuesta is None:
            continue
        sys.stdout.buffer.write((respuesta + "\n").encode("utf-8", "backslashreplace"))
        sys.stdout.flush()


if __name__ == "__main__":
    main()
