#!/usr/bin/env python3
"""Servidor MCP stdio para LFM3-Omni — esqueleto del cascarón (F2).

Declara la frontera del CONTRATO lfm3-omni/mcp-tools v1 (transporte
stdio, ADR-002) y responde handshake y descubrimiento de tools. Las
tools/call fallan cerrado hasta que F3-1 implemente la delegación al
motor: un esqueleto que promete y no cumple sería un placeholder.

Referencias: docs/contracts/mcp-tools-v1.md, docs/specs/SPEC-2-mcp.md.
"""

import json
import sys

PROTO_DEFECTO = "2025-06-18"

TOOLS = [
    {
        "name": "health",
        "description": "Estado del motor LFM3-Omni (arriba/abajo, modelo, puerto)",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "infer_text",
        "description": "Inferencia de texto con esquema de salida opcional",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "minLength": 1, "maxLength": 8000},
                "schema": {"type": "object"},
                "max_tokens": {"type": "integer", "minimum": 1, "maximum": 4096},
            },
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
                "prompt": {"type": "string", "minLength": 1},
            },
            "required": ["image_base64", "prompt"],
        },
    },
]


def responder(msg_id, resultado=None, error=None):
    cuerpo = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        cuerpo["error"] = error
    else:
        cuerpo["result"] = resultado
    return json.dumps(cuerpo, ensure_ascii=False)


def handle_initialize(msg):
    pedido = (msg.get("params") or {}).get("protocolVersion", PROTO_DEFECTO)
    return {
        "protocolVersion": pedido,
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "lfm3-omni-mcp", "version": "0.1.0"},
    }


def handle_tools_list(_msg):
    return {"tools": TOOLS}


def handle_tools_call(msg):
    # Esqueleto F2: falla cerrado; F3-1 (PLAN LFM3-1) implementa la
    # delegación al motor con validación en frontera (REQ-7).
    pedido = (msg.get("params") or {}).get("name", "")
    texto = "tool no implementada: delegación al motor llega en F3-1 (PLAN LFM3-1)"
    if pedido in ("health", "infer_text", "infer_vision"):
        texto = f"{texto} — tool pedida: {pedido}"
    return {
        "content": [{"type": "text", "text": texto}],
        "isError": True,
    }


DESPACHO = {
    "initialize": handle_initialize,
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
}


def procesar(linea):
    try:
        msg = json.loads(linea)
    except json.JSONDecodeError as exc:
        return responder(None, error={"code": -32700, "message": f"parse error: {exc}"})
    metodo = msg.get("method", "")
    handler = DESPACHO.get(metodo)
    if handler is None:
        return responder(
            msg.get("id"),
            error={"code": -32601, "message": f"método no conocido: {metodo}"},
        )
    return responder(msg.get("id"), resultado=handler(msg))


def main():
    for linea in sys.stdin:
        linea = linea.strip()
        if not linea:
            continue
        sys.stdout.write(procesar(linea) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
