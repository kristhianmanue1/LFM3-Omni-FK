#!/usr/bin/env python3
"""Cliente de demostración MCP v2 sobre transporte stdio (SPEC-i1-vm §4).

Lanza src/mcp_server_v2.py como subproceso, negocia initialize por stdin/stdout,
lista las herramientas omnimodales y consulta health y capacidades.
Exit 0 si toda la interacción pasa.

Uso: python3.12 examples/cliente_mcp_v2.py [puerto_gateway]
"""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PUERTO = int(sys.argv[1]) if len(sys.argv) > 1 else 8092


def _comunicar(proc, msg):
    linea = json.dumps(msg, ensure_ascii=False) + "\n"
    proc.stdin.write(linea.encode("utf-8"))
    proc.stdin.flush()
    respuesta_linea = proc.stdout.readline()
    if not respuesta_linea:
        raise EOFError("subproceso MCP cerró stdout")
    return json.loads(respuesta_linea.decode("utf-8"))


def main():
    env = os.environ.copy()
    env["LFM3_GATEWAY_PORT"] = str(PUERTO)
    env["PYTHONUNBUFFERED"] = "1"

    cmd = [sys.executable, str(RAIZ / "src" / "mcp_server_v2.py")]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    try:
        # 1. Initialize
        resp_init = _comunicar(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            },
        )
        assert resp_init.get("result", {}).get("protocolVersion") == "2025-06-18", (
            f"Fallo en initialize: {resp_init}"
        )
        print("MCP v2: initialize OK")

        # 2. Tools list
        resp_tools = _comunicar(
            proc,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        herramientas = [
            t["name"] for t in resp_tools.get("result", {}).get("tools", [])
        ]
        assert "health" in herramientas and "synthesize_speech" in herramientas, (
            f"Herramientas incompletas: {herramientas}"
        )
        print(f"MCP v2: tools/list OK ({len(herramientas)} tools: {herramientas})")

        # 3. Health check
        resp_health = _comunicar(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "health", "arguments": {}},
            },
        )
        res_h = resp_health.get("result", {})
        assert not res_h.get("isError"), f"Health dio error: {res_h}"
        dato_h = json.loads(res_h["content"][0]["text"])
        print(
            f"MCP v2: health OK (estado={dato_h.get('state')}, "
            f"gw_port={dato_h.get('gateway_port')})"
        )

        print("MCP v2: demostración completada con éxito.")
        sys.exit(0)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    main()
