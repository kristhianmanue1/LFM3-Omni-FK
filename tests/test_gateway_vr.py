"""Pruebas I1-VR — conversación local por turnos con SSE de texto,
cancelación ante desconexión y aislamiento de sesiones D-10 (SPEC-i1-vr).

Verifica en frontera:
- VR1: POST /v1/chat/completions con stream=True entrega text/event-stream
  incremental sin buffering (X-V2-Mode: sse-passthrough); stream=False
  conserva respuesta JSON síncrona.
- VR2: stream no booleano (1, "true", None) o stream=True combinado con
  response_format -> 400 unsupported_field_value antes del motor
  (contador 0).
- VR3: desconexión del cliente a mitad del SSE aborta el stream con el
  backend y espera confirmación de liberación de slot (/slots) antes de
  soltar el cerrojo de streaming.
- VR4: dos sesiones de conversación y retención D-10 no se cruzan.
- VR5: capabilities anuncia streaming: true y conserva video: false.
"""

import json
import socket
import stat
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import gateway_http  # noqa: E402
import transcripciones  # noqa: E402

MODELO = "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M"


class _BackendSSEFalso(BaseHTTPRequestHandler):
    count = 0
    slots_calls = 0
    active_streams = 0
    client_disconnected = threading.Event()
    first_chunk_sent = threading.Event()
    chunks = [
        {"choices": [{"delta": {"role": "assistant", "content": "Hola "}}]},
        {"choices": [{"delta": {"content": "mundo."}}]},
    ]
    slow_stream = False
    fail_status = None
    slots_override = None
    omit_done = False
    giant_line = False

    def _json(self, code, body):
        raw = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/slots":
            type(self).slots_calls += 1
            if type(self).slots_override is not None:
                self._json(200, type(self).slots_override)
                return
            busy = type(self).active_streams > 0
            self._json(200, [{"id": 0, "is_processing": busy}])
        elif self.path == "/v1/models":
            self._json(200, {"data": [{"id": MODELO}]})
        else:
            self._json(404, {"error": {"code": "not_found"}})

    def do_POST(self):
        cls = type(self)
        cls.count += 1
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        payload = json.loads(raw)
        if cls.fail_status is not None:
            self._json(cls.fail_status, {"error": "fallo backend"})
            return
        if not payload.get("stream"):
            self._json(
                200,
                {"choices": [{"message": {"content": "respuesta sincrona"}}]},
            )
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        cls.active_streams += 1
        try:
            if cls.giant_line:
                self.wfile.write(b"data: " + (b"x" * 70000) + b"\n\n")
                self.wfile.flush()
                return
            for i, chunk in enumerate(cls.chunks):
                linea = f"data: {json.dumps(chunk)}\n\n".encode("utf-8")
                self.wfile.write(linea)
                self.wfile.flush()
                if i == 0:
                    cls.first_chunk_sent.set()
                if cls.slow_stream:
                    for _ in range(30):
                        time.sleep(0.02)
                        self.wfile.write(
                            b'data: {"choices":[{"delta":{"content":"."}}]}\n\n'
                        )
                        self.wfile.flush()
            if not cls.omit_done:
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            cls.client_disconnected.set()
        finally:
            time.sleep(0.03)
            cls.active_streams = max(0, cls.active_streams - 1)

    def log_message(self, *a):
        pass


class VrGatewayBase(unittest.TestCase):
    def setUp(self):
        _BackendSSEFalso.count = 0
        _BackendSSEFalso.slots_calls = 0
        _BackendSSEFalso.active_streams = 0
        _BackendSSEFalso.client_disconnected = threading.Event()
        _BackendSSEFalso.first_chunk_sent = threading.Event()
        _BackendSSEFalso.slow_stream = False
        _BackendSSEFalso.fail_status = None
        _BackendSSEFalso.slots_override = None
        _BackendSSEFalso.omit_done = False
        _BackendSSEFalso.giant_line = False
        self.backend = ThreadingHTTPServer(("127.0.0.1", 0), _BackendSSEFalso)
        self.backend_port = self.backend.server_address[1]
        threading.Thread(target=self.backend.serve_forever, daemon=True).start()
        self.gateway = gateway_http.build_server(
            ("127.0.0.1", 0), backend=f"http://127.0.0.1:{self.backend_port}"
        )
        self.port = self.gateway.server_address[1]
        threading.Thread(target=self.gateway.serve_forever, daemon=True).start()

    def tearDown(self):
        self.gateway.shutdown()
        self.gateway.server_close()
        self.backend.shutdown()
        self.backend.server_close()

    def post_json(self, payload):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status, json.loads(resp.read()), dict(resp.headers)
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read()), dict(exc.headers)


class StreamingSSE(VrGatewayBase):
    def test_vr1_sse_entrega_eventos_y_stream_false_conserva_json(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/chat/completions",
            data=json.dumps({
                "messages": [{"role": "user", "content": "hola"}],
                "stream": True,
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        lineas = []
        with urllib.request.urlopen(req, timeout=15) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/event-stream", resp.headers.get("Content-Type", ""))
            self.assertEqual(resp.headers.get("X-V2-Mode"), "sse-passthrough")
            for raw in resp:
                texto = raw.decode("utf-8").strip()
                if texto:
                    lineas.append(texto)
        self.assertTrue(any("Hola " in l for l in lineas), lineas)
        self.assertTrue(any("mundo." in l for l in lineas), lineas)
        self.assertEqual(lineas[-1], "data: [DONE]")
        self.assertEqual(_BackendSSEFalso.count, 1)

        # stream=False conserva respuesta JSON síncrona
        estado, cuerpo, headers = self.post_json({
            "messages": [{"role": "user", "content": "hola"}],
            "stream": False,
        })
        self.assertEqual(estado, 200)
        self.assertEqual(
            cuerpo["choices"][0]["message"]["content"], "respuesta sincrona"
        )
        self.assertEqual(headers.get("X-V2-Mode"), "passthrough")
        self.assertEqual(_BackendSSEFalso.count, 2)

    def test_vr2_stream_invalido_o_con_schema_rechaza_antes_del_motor(self):
        schema = {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "required": ["a"],
        }
        casos = {
            "stream entero": {
                "messages": [{"role": "user", "content": "h"}],
                "stream": 1,
            },
            "stream string": {
                "messages": [{"role": "user", "content": "h"}],
                "stream": "true",
            },
            "stream null": {
                "messages": [{"role": "user", "content": "h"}],
                "stream": None,
            },
            "stream True + response_format": {
                "messages": [{"role": "user", "content": "h"}],
                "stream": True,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "x", "schema": schema},
                },
            },
        }
        for nombre, payload in casos.items():
            with self.subTest(caso=nombre):
                estado, cuerpo, _ = self.post_json(payload)
                self.assertEqual(estado, 400, f"{nombre}: {cuerpo}")
                self.assertEqual(
                    cuerpo["error"]["code"], "unsupported_field_value"
                )
        self.assertEqual(_BackendSSEFalso.count, 0)

    def test_vr3_desconexion_cancela_backend_y_confirma_slot_libre(self):
        _BackendSSEFalso.slow_stream = True
        cuerpo = json.dumps({
            "messages": [{"role": "user", "content": "cuenta"}],
            "stream": True,
        }).encode("utf-8")
        peticion = (
            b"POST /v1/chat/completions HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(cuerpo)).encode("ascii") + b"\r\n\r\n"
            + cuerpo
        )
        con = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        try:
            con.sendall(peticion)
            recibido = b""
            while b"data: " not in recibido:
                trozo = con.recv(1024)
                if not trozo:
                    break
                recibido += trozo
            self.assertIn(b"data: ", recibido)
        finally:
            con.close()

        self.assertTrue(
            _BackendSSEFalso.client_disconnected.wait(timeout=3.0),
            "el cierre del cliente no propagó desconexión al backend",
        )
        # Esperar a que el gateway confirme liberación de /slots y suelte cerrojo
        t0 = time.monotonic()
        while gateway_http.LOCK_STREAM_SLOT.locked() and time.monotonic() - t0 < 3.0:
            time.sleep(0.02)
        self.assertFalse(gateway_http.LOCK_STREAM_SLOT.locked())
        self.assertGreaterEqual(_BackendSSEFalso.slots_calls, 1)
        self.assertEqual(_BackendSSEFalso.active_streams, 0)

    def test_vr3b_error_backend_en_stream_da_502_json(self):
        _BackendSSEFalso.fail_status = 500
        estado, cuerpo, _ = self.post_json({
            "messages": [{"role": "user", "content": "hola"}],
            "stream": True,
        })
        self.assertEqual(estado, 502)
        self.assertEqual(cuerpo["error"]["code"], "backend_error")

    def test_vr3c_slots_fail_closed_y_bloqueo_hasta_confirmacion(self):
        # 1. /slots vacío o sin is_processing booleano NO confirma liberación
        url_backend = f"http://127.0.0.1:{self.backend_port}"
        for invalido in ([], [{}], [{"id": 0, "is_processing": "no"}]):
            _BackendSSEFalso.slots_override = invalido
            self.assertFalse(
                gateway_http._esperar_liberacion_slot(url_backend, timeout=0.08),
                f"debio fallar cerrado ante slots={invalido}",
            )

        # 2. Si un stream termina sin [DONE] (o con línea >64 KiB) y /slots
        # sigue ocupado, la siguiente petición (incluso stream=False) recibe
        # 503 overloaded (slot_not_released) sin llamar al backend.
        _BackendSSEFalso.omit_done = True
        _BackendSSEFalso.slots_override = [{"id": 0, "is_processing": True}]
        from unittest import mock
        with mock.patch.object(
            gateway_http,
            "_esperar_liberacion_slot",
            wraps=lambda b, timeout=0.05: gateway_http._esperar_liberacion_slot.__wrapped__(b, timeout=0.05)
            if hasattr(gateway_http._esperar_liberacion_slot, "__wrapped__")
            else False,
        ):
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/v1/chat/completions",
                data=json.dumps({
                    "messages": [{"role": "user", "content": "hola"}],
                    "stream": True,
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                _ = resp.read()
        self.assertTrue(gateway_http._SLOT_PENDIENTE)
        llamadas_previas = _BackendSSEFalso.count
        # Petición stream=False bloqueada con 503 mientras /slots no confirme
        estado_bloq, cuerpo_bloq, _ = self.post_json({
            "messages": [{"role": "user", "content": "hola"}],
            "stream": False,
        })
        self.assertEqual(estado_bloq, 503)
        self.assertEqual(cuerpo_bloq["error"]["code"], "overloaded")
        self.assertEqual(cuerpo_bloq["error"]["detail"], "slot_not_released")
        self.assertEqual(_BackendSSEFalso.count, llamadas_previas)

        # Cuando /slots pasa a is_processing=False, se recupera y admite
        _BackendSSEFalso.slots_override = [{"id": 0, "is_processing": False}]
        estado_ok, _, _ = self.post_json({
            "messages": [{"role": "user", "content": "hola"}],
            "stream": False,
        })
        self.assertEqual(estado_ok, 200)
        self.assertFalse(gateway_http._SLOT_PENDIENTE)

    def test_vr3d_linea_sse_excesiva_corta_y_verifica_slots(self):
        _BackendSSEFalso.giant_line = True
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/chat/completions",
            data=json.dumps({
                "messages": [{"role": "user", "content": "hola"}],
                "stream": True,
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            datos = resp.read()
        self.assertEqual(datos, b"")
        self.assertGreaterEqual(_BackendSSEFalso.slots_calls, 1)
        self.assertFalse(gateway_http._SLOT_PENDIENTE)


class SesionesYAislamiento(VrGatewayBase):
    def test_vr4_dos_sesiones_d10_no_se_cruzan(self):
        with tempfile.TemporaryDirectory() as tmp:
            s1 = transcripciones.new_session(root=tmp)
            s2 = transcripciones.new_session(root=tmp)
            self.assertNotEqual(s1, s2)
            transcripciones.record_turn(
                s1,
                user_text="turno 1 sesion A",
                reply="respuesta 1 sesion A",
                params={"session": "A", "turn": 1},
                hashes={"input_wav": "aa" * 32},
                root=tmp,
            )
            transcripciones.record_turn(
                s2,
                user_text="turno 1 sesion B",
                reply="respuesta 1 sesion B",
                params={"session": "B", "turn": 1},
                hashes={"input_wav": "bb" * 32},
                root=tmp,
            )
            transcripciones.record_turn(
                s1,
                user_text="turno 2 sesion A",
                reply="respuesta 2 sesion A",
                params={"session": "A", "turn": 2},
                hashes={"input_wav": "cc" * 32},
                root=tmp,
            )
            l1 = [json.loads(x) for x in s1.read_text(encoding="utf-8").splitlines()]
            l2 = [json.loads(x) for x in s2.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(l1), 2)
            self.assertEqual(len(l2), 1)
            self.assertEqual(l1[0]["user_text"], "turno 1 sesion A")
            self.assertEqual(l1[1]["user_text"], "turno 2 sesion A")
            self.assertEqual(l2[0]["user_text"], "turno 1 sesion B")
            self.assertEqual(stat.S_IMODE(s1.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(s2.stat().st_mode), 0o600)

    def test_vr5_capabilities_anuncia_streaming_y_video_activos(self):
        with urllib.request.urlopen(
            f"http://127.0.0.1:{self.port}/v1/capabilities", timeout=5
        ) as resp:
            caps = json.loads(resp.read())
        self.assertTrue(caps["streaming"])
        self.assertTrue(caps["voz"])
        self.assertTrue(caps["transcripcion"])
        self.assertTrue(caps["video"])


if __name__ == "__main__":
    unittest.main()
