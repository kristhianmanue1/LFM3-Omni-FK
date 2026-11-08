#!/usr/bin/env python3
"""Controles deterministas de la sonda de motor (fix-tests-hermeticos).

Cada rama de la guarda queda fijada con un servidor falso en un puerto
efímero o con un puerto liberado a propósito: motor arriba, ausencia
verificada (conexión rehusada), respuesta malformada, 5xx, status
distinto de ok y timeout. Sólo la ausencia verificada produce
reason=None (lo único que justifica saltar); el resto son errores de
sonda con motivo (hacen fallar la guarda).
"""

from __future__ import annotations

import contextlib
import socket
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from tests.engine_probe import probe_engine  # noqa: E402


class _Canned(BaseHTTPRequestHandler):
    """Sirve la respuesta enlatada de clase (código y cuerpo fijos)."""

    status = 200
    body = b'{"status": "ok"}'

    def do_GET(self):
        try:
            self.send_response(self.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(self.body)))
            self.end_headers()
            self.wfile.write(self.body)
        except OSError:
            pass  # la sonda se fue con el timeout: no importa

    def log_message(self, *args):
        pass


class _Hanging(_Canned):
    """No responde a tiempo: fuerza el timeout de la sonda."""

    def do_GET(self):
        time.sleep(2.0)
        super().do_GET()


class _Malformed(_Canned):
    body = b'{"status": ok'


class _Error5xx(_Canned):
    status = 500
    body = b'{"error": "boom"}'


class _StatusDown(_Canned):
    body = b'{"status": "down"}'


@contextlib.contextmanager
def _serving(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/health"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class SondaMotorDeterminista(unittest.TestCase):
    """Las dos ramas de la guarda, sin depender del motor real."""

    def test_motor_arriba(self):
        with _serving(_Canned) as url:
            up, reason = probe_engine(url, timeout=2.0)
        self.assertTrue(up)
        self.assertIsNone(reason)

    def test_ausencia_verificada(self):
        # puerto efímero reservado y liberado: nada escucha ahí
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        up, reason = probe_engine(
            f"http://127.0.0.1:{port}/health", timeout=2.0)
        self.assertFalse(up)
        self.assertIsNone(
            reason,
            "una conexión rehusada es ausencia verificada, no un "
            "error de sonda")

    def test_respuesta_malformada(self):
        with _serving(_Malformed) as url:
            up, reason = probe_engine(url, timeout=2.0)
        self.assertFalse(up)
        self.assertIn("malformada", reason)

    def test_error_5xx(self):
        with _serving(_Error5xx) as url:
            up, reason = probe_engine(url, timeout=2.0)
        self.assertFalse(up)
        self.assertIn("500", reason)

    def test_status_distinto_de_ok(self):
        with _serving(_StatusDown) as url:
            up, reason = probe_engine(url, timeout=2.0)
        self.assertFalse(up)
        self.assertIn("status distinto de ok", reason)

    def test_timeout_de_sonda(self):
        with _serving(_Hanging) as url:
            up, reason = probe_engine(url, timeout=0.4)
        self.assertFalse(up)
        self.assertIn("timeout", reason)


if __name__ == "__main__":
    unittest.main()
