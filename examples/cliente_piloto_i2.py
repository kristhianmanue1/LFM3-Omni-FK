#!/usr/bin/env python3
"""Cliente de demostración y onboarding para el piloto privado HTTPS (Fase I2).

Ejemplo de integración directa con Python stdlib (cero dependencias externas):
- Conexión cifrada TLS 1.3 / 1.2 a https://127.0.0.1:8443.
- Autenticación con Token Bearer y cabecera X-Project-ID.
- Demostración de consumo para proyecto-alpha y proyecto-beta.

Uso:
    python3 examples/cliente_piloto_i2.py [--puerto 8443]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import ssl
import sys
import urllib.error
import urllib.request

TOKEN_ALPHA = "alpha-test-token-for-pilot-i2-32chars"
TOKEN_BETA = "beta-test-token-for-pilot-i2-32chars"
ROOT_DIR = Path(__file__).resolve().parent.parent
CERT_PATH = ROOT_DIR / "config" / "certs" / "cert.pem"


def hacer_peticion(
    puerto: int,
    ruta: str,
    metodo: str = "GET",
    token: str | None = None,
    project_id: str | None = None,
    payload: dict | None = None,
) -> tuple[int, dict, dict]:
    """Ejecuta una petición HTTPS con verificación de certificado local."""
    url = f"https://127.0.0.1:{puerto}{ruta}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if project_id:
        headers["X-Project-ID"] = project_id

    data = json.dumps(payload).encode("utf-8") if payload else None
    ctx = ssl.create_default_context(cafile=str(CERT_PATH))

    req = urllib.request.Request(url, data=data, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15.0) as resp:
            cuerpo = json.loads(resp.read().decode("utf-8"))
            return resp.status, cuerpo, dict(resp.headers)
    except urllib.error.HTTPError as exc:
        cuerpo = json.loads(exc.read().decode("utf-8"))
        return exc.code, cuerpo, dict(exc.headers)


def main():
    parser = argparse.ArgumentParser(description="Cliente demostrador I2")
    parser.add_argument("--puerto", type=int, default=8443, help="Puerto TLS")
    args = parser.parse_args()

    if not CERT_PATH.is_file():
        print(f"BLOQ: Certificado no encontrado en {CERT_PATH}", file=sys.stderr)
        sys.exit(1)

    print("==============================================================")
    print(" DEMOSTRACIÓN DE CONSUMO DEL PILOTO PRIVADO HTTPS (FASE I2)")
    print("==============================================================")

    # 1. Comprobación pública de salud
    print("\n[1] Verificando endpoint público de salud (/healthz)...")
    st, data, h = hacer_peticion(args.puerto, "/healthz")
    print(f"  Status: {st} | Terminador TLS: {h.get('X-TLS-Terminator')}")
    print(f"  Respuesta: {data}")

    # 2. Proyecto Alpha: Chat general
    print("\n[2] Proyecto Alpha: Inferencia de texto (/v1/chat/completions)...")
    payload_alpha = {
        "messages": [{"role": "user", "content": "Di exactamente: ALPHA_ACTIVO"}],
        "max_tokens": 10,
        "temperature": 0,
    }
    st, data, h = hacer_peticion(
        args.puerto,
        "/v1/chat/completions",
        metodo="POST",
        token=TOKEN_ALPHA,
        project_id="proyecto-alpha",
        payload=payload_alpha,
    )
    print(f"  Status: {st} | Contrato: {h.get('X-Service-Contract')} | Proyecto: {h.get('X-Project-Id')}")
    contenido = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    print(f"  Respuesta del modelo: {contenido!r}")

    # 3. Proyecto Alpha intentando Perfil D (sin scope profile:d)
    print("\n[3] Proyecto Alpha intentando propuesta robótica (sin scope profile:d)...")
    payload_robot = {
        "messages": [{"role": "user", "content": "Genera acción"}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "action_proposal",
                "schema": {
                    "type": "object",
                    "required": ["observation_id", "action"],
                    "properties": {
                        "observation_id": {"type": "string"},
                        "action": {"type": "string", "enum": ["move_forward", "stop"]},
                    },
                },
            },
        },
        "max_tokens": 10,
    }
    st, data, _ = hacer_peticion(
        args.puerto,
        "/v1/chat/completions",
        metodo="POST",
        token=TOKEN_ALPHA,
        project_id="proyecto-alpha",
        payload=payload_robot,
    )
    print(f"  Status esperado: {st} (403 Forbidden)")
    print(f"  Error devuelto: {data.get('error', {}).get('message')}")

    # 4. Proyecto Beta: Perfil D estructurado autorizado
    print("\n[4] Proyecto Beta: Propuesta estructurada de acción (Perfil D autorizado)...")
    payload_beta = {
        "messages": [{"role": "user", "content": "Genera acción para obstáculo frontal"}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "action_proposal",
                "schema": {
                    "type": "object",
                    "required": ["observation_id", "action", "confidence"],
                    "properties": {
                        "observation_id": {"type": "string"},
                        "action": {"type": "string", "enum": ["move_forward", "stop", "rotate_left"]},
                        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    },
                },
            },
        },
        "max_tokens": 40,
        "temperature": 0,
    }
    st, data, h = hacer_peticion(
        args.puerto,
        "/v1/chat/completions",
        metodo="POST",
        token=TOKEN_BETA,
        project_id="proyecto-beta",
        payload=payload_beta,
    )
    print(f"  Status: {st} | Validación v2: {h.get('X-V2-Output-Validation')} | Proyecto: {h.get('X-Project-Id')}")
    contenido = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    print(f"  Propuesta estructurada validada: {contenido}")

    # 5. Prueba de aislamiento de scope: Beta intenta TTS no autorizado
    print("\n[5] Proyecto Beta intentando síntesis de voz (sin scope speech:synthesize)...")
    st, data, _ = hacer_peticion(
        args.puerto,
        "/v1/audio/speech",
        metodo="POST",
        token=TOKEN_BETA,
        project_id="proyecto-beta",
        payload={"input": "Texto no autorizado"},
    )
    print(f"  Status esperado: {st} (403 Forbidden)")
    print(f"  Error devuelto: {data.get('error', {}).get('message')}")

    print("\nDemostración de onboarding concluida con éxito.")


if __name__ == "__main__":
    main()
