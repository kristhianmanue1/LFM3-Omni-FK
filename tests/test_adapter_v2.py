"""Pruebas de política del adaptador v2 — SPEC I0 (docs/specs/SPEC-i0-
adaptador-local-v2.md). Cada rechazo debe ocurrir ANTES del backend:
el contador del backend falso queda en cero. Sin motor real: backend
falso con contador (método de iteraciones-servicio §Método común)."""

import base64
import json
import struct
import threading
import unittest
import urllib.error
import urllib.request
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import adapter_v2  # noqa: E402  (RED: el módulo aún no existe)

MODELO = "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M"


# ---------------------------------------------------------------- imágenes

def _trozo(tipo, datos, crc=None):
    cuerpo = tipo + datos
    crc = zlib.crc32(cuerpo) if crc is None else crc
    return struct.pack(">I", len(datos)) + cuerpo + struct.pack(">I", crc)


def png_valido(ancho=8, alto=8):
    bruto = b"".join(b"\x00" + b"\xff\x00\x00" * ancho for _ in range(alto))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
        + _trozo(b"IDAT", zlib.compress(bruto))
        + _trozo(b"IEND", b"")
    )


def png_truncado():
    return png_valido()[: -len(_trozo(b"IEND", b""))]


def png_crc_malo():
    return png_valido()[:33] + _trozo(b"IHDR",
                                      struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0),
                                      crc=0) + png_valido()[33 + 25:]


def png_pixeles_excesivos():
    ancho = alto = 5000  # 25 M píxeles > presupuesto 16 777 216
    bruto = b"\x00" * ancho
    return (
        b"\x89PNG\r\n\x1a\n"
        + _trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
        + _trozo(b"IDAT", zlib.compress(bruto))
        + _trozo(b"IEND", b"")
    )


def jpeg_valido(ancho=4, alto=4):
    sof0 = struct.pack(">BHHB", 8, alto, ancho, 3) + b"\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    return (
        b"\xff\xd8\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        + b"\xff\xc0" + struct.pack(">H", len(sof0) + 2) + sof0
        + b"\xff\xda" + struct.pack(">H", 8) + b"\x01\x01\x00\x00\x3f\x00"
        + b"\x12\x34" + b"\xff\xd9"
    )


def jpeg_truncado():
    return jpeg_valido()[:-2]


def dataurl(prefix, datos):
    return "data:image/" + prefix + ";base64," + base64.b64encode(datos).decode()


# ------------------------------------------------------------- backend falso

class _BackendFalso(BaseHTTPRequestHandler):
    """Backend con contador de llamadas; responde JSON canned."""

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

    def log_message(self, *a):  # silencio en pruebas
        pass


class AdapterBase(unittest.TestCase):
    def setUp(self):
        self.backend = ThreadingHTTPServer(("127.0.0.1", 0), _BackendFalso)
        self.backend_port = self.backend.server_address[1]
        threading.Thread(target=self.backend.serve_forever, daemon=True).start()
        _BackendFalso.count = 0
        self.adapter = adapter_v2.build_server(
            ("127.0.0.1", 0), backend=f"http://127.0.0.1:{self.backend_port}")
        self.port = self.adapter.server_address[1]
        threading.Thread(target=self.adapter.serve_forever, daemon=True).start()

    def tearDown(self):
        self.adapter.shutdown()
        self.backend.shutdown()

    def post(self, payload, ruta="/v1/chat/completions", crudo=None):
        data = crudo if crudo is not None else json.dumps(payload).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{ruta}", data=data,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status, json.loads(resp.read()), dict(resp.headers)
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read()), dict(exc.headers)

    def contador(self):
        return _BackendFalso.count

    def assertSinBackend(self, estado, cuerpo):
        self.assertIn(estado, (400, 404, 502))
        self.assertEqual(self.contador(), 0, "el rechazo llegó al backend")
        self.assertIn("error", cuerpo)


class PoliticaAdapter(AdapterBase):
    def test_r1_campo_desconocido(self):
        e, c, _ = self.post({"messages": [{"role": "user", "content": "h"}],
                             "seed": 7})
        self.assertSinBackend(e, c)
        self.assertEqual(c["error"]["code"], "unknown_field")

    def test_r2_schema_anidado(self):
        schema = {"type": "object", "properties": {"a": {"type": "object"}}}
        e, c, _ = self.post({"messages": [{"role": "user", "content": "h"}],
                             "response_format": {"type": "json_schema",
                                                 "json_schema": {"name": "x", "schema": schema}}})
        self.assertSinBackend(e, c)
        self.assertEqual(c["error"]["code"], "unsupported_schema")

    def test_r3_tipo_no_string_y_bool_como_number(self):
        schema_mal = {"type": "object", "properties": {"a": {"type": True}}}
        e, c, _ = self.post({"messages": [{"role": "user", "content": "h"}],
                             "response_format": {"type": "json_schema",
                                                 "json_schema": {"name": "x", "schema": schema_mal}}})
        self.assertSinBackend(e, c)
        self.assertEqual(c["error"]["code"], "unsupported_schema")
        # salida: true no satisface number (validación de salida)
        _BackendFalso.canned = {"choices": [{"message": {"content": "{\"n\": true}"}}]}
        schema = {"type": "object", "properties": {"n": {"type": "number"}}}
        e, c, _ = self.post({"messages": [{"role": "user", "content": "h"}],
                             "max_tokens": 16,
                             "response_format": {"type": "json_schema",
                                                 "json_schema": {"name": "x", "schema": schema}}})
        self.assertEqual(e, 502)
        self.assertEqual(c["error"]["code"], "output_not_valid")
        self.assertEqual(_BackendFalso.count, 1)

    def test_r4_additional_properties(self):
        schema = {"type": "object", "properties": {"a": {"type": "string"}},
                  "additionalProperties": False}
        e, c, _ = self.post({"messages": [{"role": "user", "content": "h"}],
                             "response_format": {"type": "json_schema",
                                                 "json_schema": {"name": "x", "schema": schema}}})
        self.assertSinBackend(e, c)
        self.assertEqual(c["error"]["code"], "unsupported_schema")

    def test_r5_url_externa(self):
        for url in ("https://ejemplo.com/a.png", "http://127.0.0.1:8091/x.png",
                    "data:text/plain;base64,SG9sYQ=="):
            e, c, _ = self.post({"messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": url}},
                {"type": "text", "text": "desc"}]}]})
            self.assertSinBackend(e, c)
            self.assertEqual(c["error"]["code"], "external_url_rejected", url)

    def test_r6_imagenes_truncadas(self):
        for url in (dataurl("png", png_truncado()),
                    dataurl("jpeg", jpeg_truncado())):
            e, c, _ = self.post({"messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": url}},
                {"type": "text", "text": "desc"}]}]})
            self.assertSinBackend(e, c)
            self.assertEqual(c["error"]["code"], "invalid_image", url)

    def test_r7_firma_falsa(self):
        e, c, _ = self.post({"messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": dataurl("png", png_crc_malo())}},
            {"type": "text", "text": "desc"}]}]})
        self.assertSinBackend(e, c)
        self.assertEqual(c["error"]["code"], "invalid_image")

    def test_r8_exceso_de_pixeles(self):
        e, c, _ = self.post({"messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": dataurl("png", png_pixeles_excesivos())}},
            {"type": "text", "text": "desc"}]}]})
        self.assertSinBackend(e, c)
        self.assertEqual(c["error"]["code"], "invalid_image")

    def test_r9_json_malformado_y_sin_messages(self):
        e, c, _ = self.post(None, crudo=b"{invalid")
        self.assertSinBackend(e, c)
        self.assertEqual(c["error"]["code"], "invalid_json")
        e, c, _ = self.post({})
        self.assertSinBackend(e, c)
        self.assertEqual(c["error"]["code"], "missing_messages")

    def test_r10_salida_parcial(self):
        _BackendFalso.canned = {"choices": [{"message": {"content": "{\"nombre\": \"An"}}]}
        schema = {"type": "object",
                  "properties": {"nombre": {"type": "string"}}, "required": ["nombre"]}
        e, c, _ = self.post({"messages": [{"role": "user", "content": "h"}],
                             "max_tokens": 4,
                             "response_format": {"type": "json_schema",
                                                 "json_schema": {"name": "x", "schema": schema}}})
        self.assertEqual(e, 502)
        self.assertEqual(c["error"]["code"], "output_not_valid")
        self.assertIn("raw_content", c["error"])  # estado incompleto visible

    def test_r11_passthrough_valido(self):
        e, c, h = self.post({"messages": [{"role": "user", "content": "hola"}],
                             "max_tokens": 8})
        self.assertEqual(e, 200)
        self.assertEqual(self.contador(), 1)
        self.assertEqual(c, _BackendFalso.canned)

    def test_r12_salida_estructurada_valida(self):
        _BackendFalso.canned = {"choices": [{"message": {"content": "{\"nombre\": \"Ana\"}"}}]}
        schema = {"type": "object",
                  "properties": {"nombre": {"type": "string"}}, "required": ["nombre"]}
        e, c, h = self.post({"messages": [{"role": "user", "content": "h"}],
                             "max_tokens": 16,
                             "response_format": {"type": "json_schema",
                                                 "json_schema": {"name": "x", "schema": schema}}})
        self.assertEqual(e, 200)
        self.assertEqual(self.contador(), 1)
        self.assertEqual(h.get("X-V2-Output-Validation"), "valid")

    def test_r10b_backend_ilegible(self):
        _BackendFalso.canned = {"choices": [{"message": {"content": None}}]}
        schema = {"type": "object", "properties": {"a": {"type": "string"}}}
        e, c, _ = self.post({"messages": [{"role": "user", "content": "h"}],
                             "max_tokens": 4,
                             "response_format": {"type": "json_schema",
                                                 "json_schema": {"name": "x",
                                                                 "schema": schema}}})
        self.assertEqual(e, 502)
        self.assertEqual(c["error"]["code"], "backend_error")
        self.assertEqual(self.contador(), 1)

    def test_r3c_salida_nan_no_es_valida(self):
        _BackendFalso.canned = {"choices": [{"message": {"content": "{\"n\": NaN}"}}]}
        schema = {"type": "object", "properties": {"n": {"type": "number"}}}
        e, c, _ = self.post({"messages": [{"role": "user", "content": "h"}],
                             "max_tokens": 8,
                             "response_format": {"type": "json_schema",
                                                 "json_schema": {"name": "x",
                                                                 "schema": schema}}})
        self.assertEqual(e, 502)
        self.assertEqual(c["error"]["code"], "output_not_valid")
        self.assertEqual(self.contador(), 1)

    def test_r21_entrada_nan_rechazada_sin_backend(self):
        crudo = (b'{"messages":[{"role":"user","content":"h"}],'
                 b'"tools":[{"limit":NaN}]}')
        e, c, _ = self.post(None, crudo=crudo)
        self.assertSinBackend(e, c)
        self.assertEqual(c["error"]["code"], "invalid_json")

    def test_r6c_png_con_basura_tras_iend(self):
        datos = png_valido() + b"basura"
        e, c, _ = self.post({"messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": dataurl("png", datos)}},
            {"type": "text", "text": "desc"}]}]})
        self.assertSinBackend(e, c)
        self.assertEqual(c["error"]["code"], "invalid_image")

    def test_r5b_image_url_con_clave_extra(self):
        e, c, _ = self.post({"messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": dataurl("png", png_valido()),
                                                "detail": "high"}},
            {"type": "text", "text": "desc"}]}]})
        self.assertSinBackend(e, c)
        self.assertEqual(c["error"]["code"], "unknown_content_type")

    def test_r9b_cl_no_ascii(self):
        import socket
        con = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        try:
            con.sendall(b"POST /v1/chat/completions HTTP/1.0\r\n"
                        b"Content-Length: \xc2\xb2\r\n\r\n{}")
            respuesta = con.recv(4096).decode("latin-1")
        finally:
            con.close()
        self.assertIn("400", respuesta.splitlines()[0])
        self.assertEqual(self.contador(), 0)

    def test_rutas_y_stream(self):
        e, c, _ = self.post(None, ruta="/props", crudo=b"{}")
        self.assertSinBackend(e, c)
        self.assertEqual(c["error"]["code"], "not_found")
        e, c, _ = self.post({"messages": [{"role": "user", "content": "h"}],
                             "stream": True})
        self.assertSinBackend(e, c)
        self.assertEqual(c["error"]["code"], "unsupported_field_value")


if __name__ == "__main__":
    unittest.main()
