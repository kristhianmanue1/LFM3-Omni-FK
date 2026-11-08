#!/usr/bin/env python3
"""Controles deterministas de la sonda de motor (fix-tests-hermeticos).

Cada rama de la guarda queda fijada de forma determinista: las ramas con
respuesta usan servidores falsos en puertos efímeros (motor arriba,
respuesta malformada, 5xx, status distinto de ok y timeout) y la rama de
ausencia verificada simula la conexión rehusada con ``mock`` (sin liberar
un puerto real que otro proceso pudiera ocupar — hallazgo 5 de la ronda
2). Sólo la ausencia verificada produce ``reason=None`` (lo único que
justifica saltar); el resto son errores de sonda con motivo (hacen fallar
la guarda).
"""

from __future__ import annotations

import contextlib
import sys
import threading
import time
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

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


class DeterministicEngineProbe(unittest.TestCase):
    """Las ramas de la guarda, sin depender del motor real."""

    def test_engine_up(self):
        with _serving(_Canned) as url:
            up, reason = probe_engine(url, timeout=2.0)
        self.assertTrue(up)
        self.assertIsNone(reason)

    def test_verified_absence(self):
        # conexión rehusada simulada: ausencia verificada determinista,
        # sin puerto real liberado que otro proceso pudiera ocupar
        with mock.patch(
                "urllib.request.urlopen",
                side_effect=urllib.error.URLError(ConnectionRefusedError())):
            up, reason = probe_engine(
                "http://127.0.0.1:8091/health", timeout=1.0)
        self.assertFalse(up)
        self.assertIsNone(
            reason,
            "una conexión rehusada es ausencia verificada, no un "
            "error de sonda")

    def test_transport_error_is_not_absence(self):
        # un error de transporte distinto de la conexión rehusada NO es
        # ausencia: la guarda debe fallar con su motivo, nunca saltar
        with mock.patch(
                "urllib.request.urlopen",
                side_effect=urllib.error.URLError(TimeoutError("forced"))):
            up, reason = probe_engine(
                "http://127.0.0.1:8091/health", timeout=1.0)
        self.assertFalse(up)
        self.assertIsNotNone(
            reason, "un error de sonda se tomó como ausencia verificada")
        self.assertIn("error de sonda", reason)

    def test_malformed_response(self):
        with _serving(_Malformed) as url:
            up, reason = probe_engine(url, timeout=2.0)
        self.assertFalse(up)
        self.assertIsNotNone(reason)
        self.assertIn("malformada", reason)

    def test_error_5xx(self):
        with _serving(_Error5xx) as url:
            up, reason = probe_engine(url, timeout=2.0)
        self.assertFalse(up)
        self.assertIsNotNone(reason)
        self.assertIn("500", reason)

    def test_status_not_ok(self):
        with _serving(_StatusDown) as url:
            up, reason = probe_engine(url, timeout=2.0)
        self.assertFalse(up)
        self.assertIsNotNone(reason)
        self.assertIn("status distinto de ok", reason)

    def test_probe_timeout(self):
        with _serving(_Hanging) as url:
            up, reason = probe_engine(url, timeout=0.4)
        self.assertFalse(up)
        self.assertIsNotNone(reason)
        self.assertIn("timeout", reason)


if __name__ == "__main__":
    unittest.main()
