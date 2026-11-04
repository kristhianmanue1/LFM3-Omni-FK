#!/usr/bin/env python3
"""Gateway HTTP del servicio compartido — transporte loopback
(SPEC I1, ADR-005). Políticas en gateway_core; aquí sólo transporte:
enrutado con allowlist, límites de transporte antes de costos
(compresión y chunked rechazados sin leer), proxy al motor v1 y
validación de salida estructurada.

Sin dependencias: stdlib 3.12+. Puerto default 8092
(LFM3_GATEWAY_PORT para tests); colisión → BLOQ + exit 1.
"""

import json
import os
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.error
import urllib.request

from gateway_core import (
    BACKEND_TIMEOUT_S, CAPABILITIES, DEFAULT_BACKEND, DEFAULT_PORT,
    MAX_BODY_BYTES, RUTAS_PERMITIDAS, ErrorV2, _error, _rechazar_constante,
    validar_payload, validar_salida,
)


def _enrutar(metodo, ruta):
    """Allowlist ÚNICO de enrutado (SPEC-i1 §2): una ruta sólo responde
    si el par método+ruta está en RUTAS_PERMITIDAS; añadir un if/elif
    sin la tupla queda cortado aquí por diseño."""
    if f"{metodo} {ruta}" not in set(RUTAS_PERMITIDAS):
        _error(404, "not_found", "ruta fuera del allowlist")


def _proxy(backend, ruta, cuerpo=None, timeout=BACKEND_TIMEOUT_S):
    req = urllib.request.Request(
        backend + ruta,
        data=cuerpo,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        _error(502, "backend_error", "motor inalcanzable",
               detail="backend_unreachable")


class ManejadorGateway(BaseHTTPRequestHandler):
    server_version = "lfm3-gateway-i1/0.1"

    def _json(self, status, crudo, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(crudo)))
        self.send_header("X-Request-Id", self.request_id)
        for clave, valor in (headers or {}).items():
            self.send_header(clave, valor)
        self.end_headers()
        self.wfile.write(crudo)

    def _cuerpo_error(self, exc):
        crudo = json.dumps(exc.cuerpo(self.request_id)).encode()
        self.close_connection = True
        self.send_response(exc.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(crudo)))
        self.send_header("X-Request-Id", self.request_id)
        self.end_headers()
        self.wfile.write(crudo)

    def do_GET(self):
        self.request_id = uuid.uuid4().hex
        try:
            _enrutar("GET", self.path)
            if self.path == "/healthz":
                self._json(200, b'{"status": "ok", "mode": "gateway-i1"}')
            elif self.path == "/v1/capabilities":
                self._json(200, json.dumps(CAPABILITIES).encode())
            elif self.path == "/v1/models":
                estado, cuerpo = _proxy(self.server.backend, "/v1/models",
                                        timeout=10)
                self._json(estado, cuerpo)
            else:
                _error(404, "not_found", "ruta fuera del allowlist")
        except ErrorV2 as exc:
            self._cuerpo_error(exc)

    def do_POST(self):
        self.request_id = uuid.uuid4().hex
        try:
            _enrutar("POST", self.path)
            # Límites de transporte antes de costo (SPEC-i1 §4):
            # compresión rechazada sin leer; TE chunked rechazado aunque
            # venga con Content-Length; sin CL → 400.
            if (self.headers.get("Transfer-Encoding") or "").strip():
                _error(400, "payload_too_large",
                       "Transfer-Encoding no admitido",
                       detail="content_length_required")
            codificacion = (self.headers.get("Content-Encoding")
                            or "identity").strip().lower()
            if codificacion not in ("identity", ""):
                _error(400, "payload_too_large",
                       "entrada comprimida no admitida",
                       detail="compressed_input_rejected")
            longitud = self.headers.get("Content-Length")
            if longitud is None or not longitud.isascii() \
                    or not longitud.isdigit():
                _error(400, "payload_too_large",
                       "Content-Length requerido (chunked no admitido)",
                       detail="content_length_required")
            if int(longitud) > MAX_BODY_BYTES:
                _error(413, "payload_too_large", "cuerpo sobre el presupuesto")
            crudo = self.rfile.read(int(longitud))
            try:
                payload = json.loads(crudo, parse_constant=_rechazar_constante)
            except (json.JSONDecodeError, ValueError):
                _error(400, "invalid_json",
                       "JSON malformado o con constantes no-JSON")
            validar_payload(payload)
            try:
                limpio = json.dumps(payload, allow_nan=False)
            except (TypeError, ValueError):
                _error(400, "invalid_json",
                       "el cuerpo contiene valores no representables en JSON")
            formato = payload.get("response_format")
            estado, cuerpo = _proxy(self.server.backend,
                                    "/v1/chat/completions",
                                    limpio.encode("utf-8"))
            if estado != 200:
                _error(502, "backend_error", "el motor rechazó la petición",
                       detail=f"backend_status_{estado}")
            if formato is None:
                self._json(200, cuerpo, {"X-V2-Mode": "passthrough"})
                return
            schema = formato["json_schema"]["schema"]
            try:
                respuesta = json.loads(cuerpo,
                                       parse_constant=_rechazar_constante)
                contenido = respuesta["choices"][0]["message"]["content"]
            except (json.JSONDecodeError, KeyError, IndexError, TypeError,
                    ValueError):
                _error(502, "backend_error", "respuesta del motor ilegible",
                       detail="backend_shape")
            if not isinstance(contenido, str):
                _error(502, "backend_error", "respuesta del motor ilegible",
                       detail="backend_shape")
            validar_salida(contenido, schema)
            self._json(200, cuerpo, {"X-V2-Output-Validation": "valid"})
        except ErrorV2 as exc:
            self._cuerpo_error(exc)

    def _metodo_no_soportado(self):
        self.request_id = uuid.uuid4().hex
        try:
            _error(404, "not_found", "método fuera del allowlist")
        except ErrorV2 as exc:
            self._cuerpo_error(exc)

    do_PUT = _metodo_no_soportado
    do_DELETE = _metodo_no_soportado
    do_PATCH = _metodo_no_soportado
    do_OPTIONS = _metodo_no_soportado

    def log_message(self, formato, *args):  # sin paths ni payload en logs
        pass


class ServidorGateway(ThreadingHTTPServer):
    daemon_threads = True


def build_server(direccion, backend=DEFAULT_BACKEND):
    servidor = ServidorGateway(direccion, ManejadorGateway)
    servidor.backend = backend
    return servidor


def main():
    # Puerto: affordance vigente LFM3_GATEWAY_PORT, con compatibilidad
    # de la affordance histórica LFM3_ADAPTER_PORT (SPEC-i0 §1).
    bruto = (os.environ.get("LFM3_GATEWAY_PORT")
             or os.environ.get("LFM3_ADAPTER_PORT")
             or str(DEFAULT_PORT))
    backend = os.environ.get("LFM3_BACKEND", DEFAULT_BACKEND)
    try:
        puerto = int(bruto)
        servidor = build_server(("127.0.0.1", puerto), backend)
    except (OSError, ValueError, OverflowError) as exc:
        print(f"BLOQ: puerto {bruto!r} no disponible ({exc}); "
              f"no se asume puerto libre", file=sys.stderr)
        sys.exit(1)
    print(f"gateway i1 en 127.0.0.1:{puerto} -> {backend}", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
