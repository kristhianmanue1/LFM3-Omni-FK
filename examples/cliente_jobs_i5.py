#!/usr/bin/env python3
"""Cliente de demostración y referencia para Trabajos Largos (Perfil J) — Fase I5.

Demuestra el consumo del Perfil J (especificación SPEC-i5):
1. Envío de trabajo en segundo plano con cabecera Idempotency-Key.
2. Demostración de idempotencia: reintento con mismo cuerpo devuelve 202 y mismo job_id.
3. Detección de conflicto 409 ante clave reutilizada con payload diferente.
4. Consulta de estado y recuperación del resultado con GET /jobs/{id}.
5. Cancelación segura de trabajos con DELETE /jobs/{id}.
6. Aislamiento estricto multi-inquilino (404 si otro proyecto intenta consultar).

Cero dependencias externas: 100% Python estándar (urllib, json, ssl, time).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import ssl
import sys
import time
import urllib.error
import urllib.request
import uuid

DEFAULT_PORT = 8092
TOKEN_ALPHA = os.environ.get("LFM3_AUTH_TOKEN_ALPHA", "alpha-test-token-for-pilot-i2-32chars")
TOKEN_BETA = os.environ.get("LFM3_AUTH_TOKEN_BETA", "beta-test-token-for-pilot-i2-32chars")
ROOT_DIR = Path(__file__).resolve().parent.parent
CERT_PATH = ROOT_DIR / "config" / "certs" / "cert.pem"


class JobsClient:
    """Cliente HTTP para interactuar con la API de trabajos largos (Perfil J)."""

    def __init__(
        self,
        base_url: str = f"http://127.0.0.1:{DEFAULT_PORT}",
        auth_token: str | None = TOKEN_ALPHA,
        project_id: str = "proyecto-alpha",
        insecure_tls: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.project_id = project_id
        self.ssl_context = None
        if self.base_url.startswith("https://"):
            if insecure_tls:
                self.ssl_context = ssl._create_unverified_context()
            elif CERT_PATH.exists():
                self.ssl_context = ssl.create_default_context(cafile=str(CERT_PATH))
            else:
                self.ssl_context = ssl.create_default_context()

    def _headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        if self.project_id:
            headers["X-Project-ID"] = self.project_id
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def submit_job(
        self,
        operation: str,
        payload: dict,
        idempotency_key: str,
        ttl_seconds: int = 3600,
    ) -> tuple[int, dict]:
        """Envía un trabajo largo a POST /jobs."""
        url = f"{self.base_url}/jobs"
        body = {
            "operation": operation,
            "payload": payload,
            "ttl_seconds": ttl_seconds,
        }
        data = json.dumps(body).encode("utf-8")
        headers = self._headers(idempotency_key=idempotency_key)
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        kwargs = {"timeout": 15.0}
        if self.ssl_context:
            kwargs["context"] = self.ssl_context

        try:
            with urllib.request.urlopen(req, **kwargs) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            try:
                err_json = json.loads(err_body)
            except Exception:
                err_json = {"raw": err_body}
            return exc.code, err_json
        except Exception as exc:
            return 0, {"error": {"message": str(exc)}}

    def get_job(self, job_id: str) -> tuple[int, dict]:
        """Consulta el estado del trabajo en GET /jobs/{id}."""
        url = f"{self.base_url}/jobs/{job_id}"
        headers = self._headers()
        req = urllib.request.Request(url, headers=headers, method="GET")

        kwargs = {"timeout": 15.0}
        if self.ssl_context:
            kwargs["context"] = self.ssl_context

        try:
            with urllib.request.urlopen(req, **kwargs) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            try:
                err_json = json.loads(err_body)
            except Exception:
                err_json = {"raw": err_body}
            return exc.code, err_json
        except Exception as exc:
            return 0, {"error": {"message": str(exc)}}

    def cancel_job(self, job_id: str) -> tuple[int, dict]:
        """Solicita la cancelación de un trabajo con DELETE /jobs/{id}."""
        url = f"{self.base_url}/jobs/{job_id}"
        headers = self._headers()
        req = urllib.request.Request(url, headers=headers, method="DELETE")

        kwargs = {"timeout": 15.0}
        if self.ssl_context:
            kwargs["context"] = self.ssl_context

        try:
            with urllib.request.urlopen(req, **kwargs) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            try:
                err_json = json.loads(err_body)
            except Exception:
                err_json = {"raw": err_body}
            return exc.code, err_json
        except Exception as exc:
            return 0, {"error": {"message": str(exc)}}


def ejecutar_demostracion(cliente: JobsClient, beta_token: str | None = None) -> int:
    print("=" * 60)
    print("Demostración de Trabajos Largos (Perfil J - SDK LFM3-Omni)")
    print(f"Destino: {cliente.base_url} (Proyecto: {cliente.project_id})")
    print("=" * 60)

    idemp_key = f"key-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    payload_tarea = {
        "messages": [{"role": "user", "content": "Genera un resumen analítico exhaustivo."}],
        "max_tokens": 512,
        "temperature": 0.0,
    }

    # 1. Enviar trabajo largo
    print(f"\n[1] Enviando POST /jobs (Idempotency-Key: {idemp_key})...")
    status, res = cliente.submit_job("infer_text", payload_tarea, idemp_key)
    print(f"    Respuesta: HTTP {status} -> {res}")
    if status != 202:
        print("    Fallo en admisión de job")
        return 1
    job_id = res["job_id"]

    # 2. Reintento idempotente con mismo payload
    print(f"\n[2] Reintentando con misma Idempotency-Key y mismo payload...")
    status_dup, res_dup = cliente.submit_job("infer_text", payload_tarea, idemp_key)
    print(f"    Respuesta: HTTP {status_dup} -> {res_dup}")
    assert status_dup == 202 and res_dup.get("job_id") == job_id, "Fallo en garantía de idempotencia"
    print("    Garantía de Idempotencia: OK (mismo job_id devuelto sin duplicar)")

    # 3. Conflicto con clave reutilizada y cuerpo diferente
    print(f"\n[3] Provocando conflicto con misma Idempotency-Key y payload diferente...")
    payload_distinto = {
        "messages": [{"role": "user", "content": "Instrucción completamente distinta."}],
        "max_tokens": 128,
        "temperature": 0.0,
    }
    status_conf, res_conf = cliente.submit_job("infer_text", payload_distinto, idemp_key)
    print(f"    Respuesta: HTTP {status_conf} -> {res_conf}")
    assert status_conf == 409, f"Se esperaba HTTP 409, obtenido {status_conf}"
    print("    Detección de Conflicto 409: OK (idempotency_conflict capturado)")

    # 4. Consulta de estado GET /jobs/{id}
    print(f"\n[4] Consultando GET /jobs/{job_id}...")
    status_get, res_get = cliente.get_job(job_id)
    print(f"    Respuesta: HTTP {status_get} -> Estado: {res_get.get('state')}")
    assert status_get == 200 and res_get.get("job_id") == job_id, "Fallo en consulta de job"

    # 5. Aislamiento multi-inquilino (Proyecto Beta no puede ver el job de Proyecto Alpha)
    print("\n[5] Verificando aislamiento multi-inquilino desde Proyecto Beta...")
    b_token = beta_token or TOKEN_BETA
    cliente_beta = JobsClient(
        base_url=cliente.base_url,
        auth_token=b_token,
        project_id="proyecto-beta",
        insecure_tls=True,
    )
    status_beta, res_beta = cliente_beta.get_job(job_id)
    print(f"    Consulta desde Beta: HTTP {status_beta} -> {res_beta}")
    assert status_beta == 404, f"Fallo de aislamiento: Beta recibió HTTP {status_beta} en vez de 404"
    print("    Aislamiento Multi-inquilino: OK (HTTP 404 fail-closed garantizado)")

    # 6. Cancelación DELETE /jobs/{id}
    print(f"\n[6] Solicitando cancelación DELETE /jobs/{job_id}...")
    status_del, res_del = cliente.cancel_job(job_id)
    print(f"    Respuesta cancelación: HTTP {status_del} -> {res_del}")
    assert status_del == 200, f"Fallo en cancelación: {res_del}"
    print("    Cancelación: OK")

    print("\nDemostración de Perfil J completada con éxito.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Cliente SDK Perfil J (Jobs)")
    parser.add_argument("--url", default=f"http://127.0.0.1:{DEFAULT_PORT}")
    parser.add_argument("--token", default=TOKEN_ALPHA)
    parser.add_argument("--project", default="proyecto-alpha")
    parser.add_argument("--beta-token", default=None)
    parser.add_argument("--insecure", action="store_true")
    args = parser.parse_args()

    client = JobsClient(
        base_url=args.url,
        auth_token=args.token,
        project_id=args.project,
        insecure_tls=args.insecure,
    )
    sys.exit(ejecutar_demostracion(client, beta_token=args.beta_token))


if __name__ == "__main__":
    main()
