#!/usr/bin/env python3
"""Terminador TLS en Python stdlib para el piloto privado HTTPS (Fase I2).

Implementa SPEC-i2-piloto-privado (§3.1) y ADR-009:
- Cero dependencias externas (Python 3.12+ stdlib: ssl, http.server).
- Escucha HTTPS en puerto 8443 (o LFM3_TLS_PORT) con TLS 1.3 / TLS 1.2 estricto.
- Reenvía el tráfico autenticado hacia el gateway loopback en 127.0.0.1:8092.
- Generación o carga de certificados locales con SAN localhost / lfm3.local
  y permisos 0600 en config/certs/.
"""

from __future__ import annotations

import argparse
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

DEFAULT_TLS_PORT = 8443
DEFAULT_GATEWAY_PORT = 8092
CONFIG_CERTS_DIR = Path(__file__).resolve().parent.parent / "config" / "certs"


def asegurar_certificados_locales(directorio: Path) -> tuple[Path, Path]:
    """Carga o genera certificados locales con SAN localhost y lfm3.local."""
    directorio.mkdir(parents=True, exist_ok=True)
    os.chmod(directorio, 0o700)
    cert_path = directorio / "cert.pem"
    key_path = directorio / "key.pem"

    if cert_path.is_file() and key_path.is_file():
        return cert_path, key_path

    openssl_bin = shutil.which("openssl")
    if not openssl_bin:
        raise OSError("openssl no está disponible para generar certificados locales")

    # Generar certificado autofirmado con SAN válido (localhost, lfm3.local, 127.0.0.1)
    cnf_content = (
        "[req]\n"
        "default_bits = 2048\n"
        "prompt = no\n"
        "default_md = sha256\n"
        "distinguished_name = dn\n"
        "x509_extensions = v3_req\n\n"
        "[dn]\n"
        "C = MX\n"
        "ST = CDMX\n"
        "L = Local\n"
        "O = LFM3-Omni-Pilot\n"
        "CN = localhost\n\n"
        "[v3_req]\n"
        "subjectAltName = @alt_names\n"
        "basicConstraints = CA:TRUE\n"
        "keyUsage = digitalSignature, keyEncipherment, keyCertSign\n"
        "extendedKeyUsage = serverAuth\n\n"
        "[alt_names]\n"
        "DNS.1 = localhost\n"
        "DNS.2 = lfm3.local\n"
        "IP.1 = 127.0.0.1\n"
    )

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".cnf") as cnf:
        cnf.write(cnf_content)
        cnf_path = cnf.name

    try:
        cmd = [
            openssl_bin, "req", "-x509", "-nodes", "-days", "365",
            "-newkey", "rsa:2048",
            "-keyout", str(key_path),
            "-out", str(cert_path),
            "-config", cnf_path,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise OSError(f"fallo al generar certificados: {res.stderr}")
        os.chmod(cert_path, 0o600)
        os.chmod(key_path, 0o600)
    finally:
        if os.path.exists(cnf_path):
            os.remove(cnf_path)

    return cert_path, key_path


class ManejadorProxyTLS(BaseHTTPRequestHandler):
    """Reenvía peticiones HTTPS recibidas hacia el gateway HTTP interno."""

    server_version = "lfm3-tls-terminator/0.1"

    def _reenviar(self, metodo: str) -> None:
        gateway_url = f"http://127.0.0.1:{self.server.gateway_port}{self.path}"
        req_id = self.headers.get("X-Request-Id") or f"tls-{os.urandom(8).hex()}"
        longitud_str = self.headers.get("Content-Length")
        longitud = 0
        if longitud_str is not None:
            if not longitud_str.isdigit():
                self._responder_error(400, "invalid_payload", "Content-Length inválido", req_id)
                return
            longitud = int(longitud_str)
            if longitud > 33554432:  # 32 MiB
                self._responder_error(413, "payload_too_large", "cuerpo sobre el presupuesto de 32 MiB", req_id)
                return

        cuerpo = self.rfile.read(longitud) if longitud > 0 else None

        cabeceras = {}
        for k, v in self.headers.items():
            if k.lower() not in ("host", "connection"):
                cabeceras[k] = v
        cabeceras["X-Request-Id"] = req_id

        req = urllib.request.Request(
            gateway_url,
            data=cuerpo,
            headers=cabeceras,
            method=metodo,
        )

        try:
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                estado = resp.status
                datos = resp.read()
                resp_headers = resp.headers
        except urllib.error.HTTPError as exc:
            estado = exc.code
            datos = exc.read()
            resp_headers = exc.headers
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError):
            self._responder_error(502, "backend_unreachable", "gateway loopback inalcanzable", req_id)
            return

        self.send_response(estado)
        for k, v in resp_headers.items():
            if k.lower() not in ("connection", "transfer-encoding"):
                self.send_header(k, v)
        self.send_header("X-TLS-Terminator", "lfm3-stdlib")
        self.send_header("X-Service-Contract", "2")
        self.send_header("X-Request-Id", req_id)
        self.end_headers()
        self.wfile.write(datos)

    def _responder_error(self, status: int, code: str, msg: str, req_id: str) -> None:
        err_payload = json.dumps({
            "error": {
                "code": code,
                "message": msg,
                "type": "server_error" if status >= 500 else "invalid_request_error",
                "param": None,
                "retryable": status in (429, 502, 503, 504),
                "request_id": req_id,
            }
        }).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(err_payload)))
        self.send_header("X-TLS-Terminator", "lfm3-stdlib")
        self.send_header("X-Service-Contract", "2")
        self.send_header("X-Request-Id", req_id)
        self.end_headers()
        self.wfile.write(err_payload)

    def do_GET(self) -> None:
        self._reenviar("GET")

    def do_POST(self) -> None:
        self._reenviar("POST")

    def do_DELETE(self) -> None:
        self._reenviar("DELETE")

    def log_message(self, *a) -> None:
        pass


class ServidorTLS(ThreadingHTTPServer):
    daemon_threads = True


def build_tls_server(
    direccion: tuple[str, int],
    gateway_port: int = DEFAULT_GATEWAY_PORT,
    certs_dir: Optional[Path] = None,
) -> ServidorTLS:
    """Construye e inicializa el servidor TLS con socket seguro configurado."""
    cert_path, key_path = asegurar_certificados_locales(certs_dir or CONFIG_CERTS_DIR)
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contexto.minimum_version = ssl.TLSVersion.TLSv1_2
    contexto.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))

    servidor = ServidorTLS(direccion, ManejadorProxyTLS)
    servidor.gateway_port = gateway_port
    servidor.socket = contexto.wrap_socket(servidor.socket, server_side=True)
    servidor.cert_path = cert_path
    servidor.key_path = key_path
    return servidor


def main() -> None:
    parser = argparse.ArgumentParser(description="Terminador TLS stdlib para LFM3-Omni")
    parser.add_argument("--tls-port", type=int, default=int(os.environ.get("LFM3_TLS_PORT", DEFAULT_TLS_PORT)),
                        help="Puerto de escucha HTTPS (default: 8443)")
    parser.add_argument("--gateway-port", type=int, default=int(os.environ.get("LFM3_GATEWAY_PORT", DEFAULT_GATEWAY_PORT)),
                        help="Puerto del gateway HTTP interno (default: 8092)")
    parser.add_argument("--host", default=os.environ.get("LFM3_TLS_HOST", "127.0.0.1"),
                        help="Host o interfaz para bind (default: 127.0.0.1)")
    args = parser.parse_args()

    try:
        servidor = build_tls_server((args.host, args.tls_port), gateway_port=args.gateway_port)
    except (OSError, ValueError) as exc:
        print(f"BLOQ: no se pudo iniciar el terminador TLS en {args.host}:{args.tls_port} ({exc})",
              file=sys.stderr)
        sys.exit(1)

    print(f"terminador TLS i2 en https://{args.host}:{args.tls_port} -> http://127.0.0.1:{args.gateway_port}",
          flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
