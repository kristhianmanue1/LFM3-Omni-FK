"""Pruebas I1 — gateway en loopback (SPEC-i1 §7). Las de transporte
comprueban límites ANTES de costo: el contador del backend falso debe
quedar en cero en todo rechazo."""

import json
import socket
import subprocess
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from gateway_core import CAPABILITIES, RUTAS_PERMITIDAS  # noqa: E402 (RED)
from gateway_http import build_server  # noqa: E402 (RED)

MODELO = "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M"


class _BackendFalso(BaseHTTPRequestHandler):
    count = 0
    canned = {"choices": [{"message": {"content": "hola"}}]}

    def _json(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        type(self).count += 1
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self._json(200, type(self).canned)

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"status": "ok"})
        elif self.path == "/v1/models":
            self._json(200, {"data": [{"id": MODELO}]})
        else:
            self._json(404, {"error": {"code": "not_found"}})

    def log_message(self, *a):
        pass


class GatewayBase(unittest.TestCase):
    def setUp(self):
        self.backend = ThreadingHTTPServer(("127.0.0.1", 0), _BackendFalso)
        self.backend_port = self.backend.server_address[1]
        threading.Thread(target=self.backend.serve_forever, daemon=True).start()
        _BackendFalso.count = 0
        self.gateway = build_server(
            ("127.0.0.1", 0), backend=f"http://127.0.0.1:{self.backend_port}")
        self.port = self.gateway.server_address[1]
        threading.Thread(target=self.gateway.serve_forever, daemon=True).start()

    def tearDown(self):
        self.gateway.shutdown()
        self.gateway.server_close()
        self.backend.shutdown()
        self.backend.server_close()

    def post(self, payload, crudo=None, cabeceras=None):
        data = crudo if crudo is not None else json.dumps(payload).encode()
        cab = {"Content-Type": "application/json"}
        cab.update(cabeceras or {})
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/chat/completions",
            data=data, headers=cab)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def get(self, ruta):
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}{ruta}", timeout=15) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def contador(self):
        return _BackendFalso.count


class Capabilities(GatewayBase):
    def test_g1_capaabilities_sin_lo_no_activo(self):
        estado, cuerpo = self.get("/v1/capabilities")
        self.assertEqual(estado, 200)
        self.assertEqual(self.contador(), 0)
        self.assertEqual(cuerpo["entrada"], ["texto", "imagen"])
        self.assertEqual(cuerpo["salida"], ["texto"])
        for clave in ("streaming", "audio", "video", "voz"):
            self.assertFalse(cuerpo[clave], f"{clave} no puede anunciarse activo")
        self.assertEqual(CAPABILITIES["version"], "i1")


class Transporte(GatewayBase):
    def test_g2_chunked_sin_content_length(self):
        cuerpo = json.dumps({"messages": [{"role": "user", "content": "h"}]}).encode()
        peticion = (b"POST /v1/chat/completions HTTP/1.0\r\n"
                    b"Transfer-Encoding: chunked\r\n"
                    b"Content-Type: application/json\r\n\r\n"
                    + f"{len(cuerpo):x}\r\n".encode() + cuerpo + b"\r\n0\r\n\r\n")
        con = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        try:
            con.sendall(peticion)
            respuesta = con.recv(65536).decode("latin-1")
        finally:
            con.close()
        self.assertIn("400", respuesta.splitlines()[0])
        self.assertIn("content_length_required", respuesta)
        self.assertEqual(self.contador(), 0)

    def test_g3_compresion_rechazada_antes_de_leer(self):
        # Sólo cabeceras, sin cuerpo: una implementación que leyera el
        # cuerpo primero se colgaría esperando bytes que nunca llegan.
        peticion = (b"POST /v1/chat/completions HTTP/1.0\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Content-Encoding: gzip\r\n"
                    b"Content-Length: 5000000\r\n\r\n")
        con = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        try:
            con.sendall(peticion)
            con.settimeout(3)
            # HTTP/1.0: leer hasta el cierre; un único recv() podía traer
            # sólo las cabeceras (intermitente, ajuste PLAN LFM3-2).
            trozos = []
            while chunk := con.recv(65536):
                trozos.append(chunk)
            respuesta = b"".join(trozos).decode("latin-1")
        finally:
            con.close()
        self.assertIn("400", respuesta.splitlines()[0])
        self.assertIn("compressed_input_rejected", respuesta)
        self.assertEqual(self.contador(), 0)


class Allowlist(GatewayBase):
    def test_g4_rutas_administrativas_no_pasan(self):
        for ruta in ("/props", "/slots", "/metrics", "/", "/ui"):
            e, c = self.get(ruta)
            self.assertEqual(e, 404, ruta)
            self.assertEqual(c["error"]["code"], "not_found")
        self.assertEqual(self.contador(), 0)
        self.assertEqual(sorted(RUTAS_PERMITIDAS), sorted([
            "POST /v1/chat/completions", "GET /v1/models",
            "GET /v1/capabilities", "GET /healthz"]))
        # equivalencia enrutado ≡ tupla: toda ruta del allowlist responde;
        # una fuera de ella es 404 aunque el código la mencione.
        from gateway_http import _enrutar
        from gateway_core import ErrorV2
        for entrada in RUTAS_PERMITIDAS:
            metodo, ruta = entrada.split(" ", 1)
            _enrutar(metodo, ruta)  # no debe levantar
        with self.assertRaises(ErrorV2):
            _enrutar("GET", "/no-existe")


class Colision(GatewayBase):
    def test_g5_puerto_ocupado_falla_cerrado(self):
        ocupado = self.port  # ya está en escucha por el gateway del fixture
        for valor in (str(ocupado), "abc", "99999"):
            proc = subprocess.run(
                [sys.executable, str(RAIZ / "src" / "gateway_http.py")],
                env={"PATH": "/usr/bin:/bin", "LFM3_GATEWAY_PORT": valor,
                     "PYTHONPATH": str(RAIZ / "src")},
                capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 1, valor)
            self.assertIn("BLOQ", proc.stdout + proc.stderr)


class FronteraInterna(unittest.TestCase):
    def test_g6_core_sin_transporte(self):
        fuente = (RAIZ / "src" / "gateway_core.py").read_text()
        self.assertNotIn("import urllib", fuente)
        self.assertNotIn("http.server", fuente)
        self.assertNotIn("socket", fuente)


if __name__ == "__main__":
    unittest.main()
