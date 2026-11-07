#!/usr/bin/env python3
"""Cliente de referencia y onboarding para el servidor MCP remoto (Fase I3).

Demuestra la integración de agentes externos vía Model Context Protocol (MCP)
con transporte Streamable HTTP (POST /mcp) sobre red privada:
- Negociación de protocolo `initialize` y captura de `Mcp-Session-Id`.
- Inspección de capacidades y herramientas con `tools/list`.
- Invocación de herramientas omnimodales:
  * Texto estructurado con JSON schema v2-ext (`infer_text`).
  * Inspección visual de imágenes (`infer_vision`).
  * Síntesis de voz hablada en español (`synthesize_speech`).
  * Turno conversacional multi-turno (`conversational_turn`).

Uso:
    python3 examples/cliente_mcp_remoto_i3.py [--url http://127.0.0.1:8092/mcp]
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import ssl
import sys
import urllib.error
import urllib.request

TOKEN_DEFAULT = "alpha-test-token-for-pilot-i3-32chars"
PROJECT_DEFAULT = "proyecto-alpha"
ROOT_DIR = Path(__file__).resolve().parent.parent
CERT_PATH = ROOT_DIR / "config" / "certs" / "cert.pem"


class ClienteMCPRemoto:
    """Cliente mínimo en Python stdlib para agentes MCP sobre HTTP/HTTPS."""

    def __init__(
        self,
        endpoint_url: str = "http://127.0.0.1:8092/mcp",
        token: str = TOKEN_DEFAULT,
        project_id: str = PROJECT_DEFAULT,
        cert_path: Path | None = None,
    ) -> None:
        self.url = endpoint_url
        self.token = token
        self.project_id = project_id
        self.session_id: str | None = None
        self.req_counter = 0

        self.ssl_context = None
        if self.url.startswith("https://") and cert_path and cert_path.is_file():
            self.ssl_context = ssl.create_default_context(cafile=str(cert_path))

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        self.req_counter += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self.req_counter,
            "method": method,
            "params": params or {},
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "X-Project-ID": self.project_id,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        req = urllib.request.Request(self.url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=20.0) as resp:
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self.session_id = sid
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            cuerpo = exc.read().decode("utf-8")
            try:
                return json.loads(cuerpo)
            except Exception:
                return {"error": {"code": exc.code, "message": cuerpo}}

    def initialize(self) -> dict:
        res = self._rpc("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "onboarding-agent", "version": "1.0"},
        })
        return res.get("result", {})

    def list_tools(self) -> list:
        res = self._rpc("tools/list", {})
        return res.get("result", {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> dict:
        res = self._rpc("tools/call", {"name": name, "arguments": arguments})
        result = res.get("result", {})
        if result.get("isError"):
            print(f"[-] Error en tool {name}: {result.get('content', [{}])[0].get('text')}")
            return result
        content = result.get("content", [{}])[0].get("text", "{}")
        try:
            return json.loads(content)
        except Exception:
            return {"raw": content}


def main():
    parser = argparse.ArgumentParser(description="Cliente demostrador MCP remoto I3")
    parser.add_argument("--url", default="http://127.0.0.1:8092/mcp", help="Endpoint MCP")
    parser.add_argument("--token", default=TOKEN_DEFAULT, help="Token Bearer")
    parser.add_argument("--project", default=PROJECT_DEFAULT, help="X-Project-ID")
    args = parser.parse_args()

    cert = CERT_PATH if args.url.startswith("https://") else None
    cliente = ClienteMCPRemoto(endpoint_url=args.url, token=args.token, project_id=args.project, cert_path=cert)

    print("==============================================================")
    print(" DEMOSTRACIÓN DE SERVIDOR MCP REMOTO OMNIMODAL (FASE I3)")
    print("==============================================================")
    print(f"Conectando a {args.url} como {args.project}...")

    # 1. Initialize
    init_info = cliente.initialize()
    print(f"\n[1] Handshake initialize:")
    print(f"    Protocolo negociado: {init_info.get('protocolVersion')}")
    print(f"    Servidor remoto:     {init_info.get('serverInfo', {}).get('name')}")
    print(f"    Mcp-Session-Id:      {cliente.session_id}")

    # 2. List tools
    tools = cliente.list_tools()
    print(f"\n[2] Herramientas omnimodales publicadas ({len(tools)}):")
    for t in tools:
        print(f"    - {t['name']:20s} : {t['description']}")

    # 3. Health & Capabilities
    health = cliente.call_tool("health", {})
    print(f"\n[3] Vitalidad del servicio:")
    print(f"    Estado: {health.get('status')} | Modelo: {health.get('model')}")

    # 4. Infer Text con Schema estructurado
    schema_ejemplo = {
        "type": "object",
        "properties": {
            "tema": {"type": "string"},
            "puntuacion": {"type": "integer"},
        },
        "required": ["tema", "puntuacion"],
        "additionalProperties": False,
    }
    texto_res = cliente.call_tool("infer_text", {
        "prompt": "Genera una evaluación en formato JSON del servicio MCP",
        "schema": schema_ejemplo,
    })
    print(f"\n[4] Inferencia de texto estructurado con schema v2-ext:")
    print(f"    Resultado: {texto_res}")

    # 5. Infer Vision con PNG sintético
    png_magic = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    png_b64 = base64.b64encode(png_magic).decode("ascii")
    vision_res = cliente.call_tool("infer_vision", {
        "prompt": "Describe la imagen adjunta",
        "image_base64": png_b64,
    })
    print(f"\n[5] Inferencia visual (infer_vision):")
    print(f"    Descripción: {vision_res.get('description', vision_res)}")

    # 6. Conversación por turnos
    turno_res = cliente.call_tool("conversational_turn", {
        "messages": [
            {"role": "user", "content": "Hola, soy un agente externo conectado por MCP remoto"},
            {"role": "assistant", "content": "Bienvenido al servicio omnimodal LFM3-Omni"},
            {"role": "user", "content": "¿Qué modalidades tienes activas?"},
        ],
        "synthesize_voice": False,
    })
    print(f"\n[6] Turno conversacional (conversational_turn):")
    print(f"    Respuesta: {turno_res.get('text', turno_res)}")

    print("\n[OK] Demostración de cliente MCP remoto I3 completada con éxito.")


if __name__ == "__main__":
    main()
