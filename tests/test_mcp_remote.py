#!/usr/bin/env python3
"""Pruebas de la Fase I3 — Servidor MCP remoto desacoplado (Streamable HTTP).

Verifica la conformidad estricta con SPEC-i3-mcp-remote y ADR-010:
1. Endpoint /mcp sobre transporte Streamable HTTP (POST / GET con SSE).
2. Autenticación Bearer, validación de scopes por herramienta y aislamiento de sesiones.
3. Catálogo omnimodal completo en tools/list:
   health, capabilities, infer_text, infer_vision, infer_audio,
   synthesize_speech, infer_video, conversational_turn.
4. Validación fail-closed en frontera contra schema v2-ext y detección de salida inválida.
5. Contención estricta de egreso (anti-SSRF): rechazo inmediato de URLs en medios.
6. Exclusión mutua de TTS: respuesta tts_busy ante colisión sin encolado.
7. Desacoplamiento de sesiones y prevención de cruce entre proyectos.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from gateway_auth import FairQueueDispatcher, TokenRegistry  # noqa: E402
from gateway_core import CAPABILITIES  # noqa: E402
from gateway_http import build_server, LOCK_TTS  # noqa: E402
from mcp_remote import MCPRemoteHandler, TOOLS_REMOTE  # noqa: E402
from mcp_server_v2 import TOOLS  # noqa: E402

TOKEN_ALPHA = "alpha-test-token-for-pilot-i3-32chars"
TOKEN_BETA = "beta-test-token-for-pilot-i3-32chars"
HASH_ALPHA = hashlib.sha256(TOKEN_ALPHA.encode()).hexdigest()
HASH_BETA = hashlib.sha256(TOKEN_BETA.encode()).hexdigest()


class BackendFalsoMCP(BaseHTTPRequestHandler):
    """Simulador de llama-server para pruebas MCP remoto."""

    def _json(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8"))

        if self.path == "/v1/chat/completions":
            msgs = payload.get("messages", [])
            last_msg = msgs[-1]["content"] if msgs else ""
            if isinstance(last_msg, list):
                last_msg = "multimodal"

            # Si se solicita schema, responder formato adecuado
            fmt = payload.get("response_format")
            if fmt and fmt.get("type") == "json_schema":
                schema_name = fmt.get("json_schema", {}).get("name", "")
                if "corrupto" in str(msgs):
                    content = '{"campo_invalido": 123}'
                else:
                    content = '{"resultado": "ok_estructurado", "valor": 42}'
            else:
                content = f"Eco LFM3: {last_msg}"

            self._json(200, {
                "id": "chatcmpl-mcp-test",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            })
            return

        self._json(404, {"error": "not_found"})

    def log_message(self, format, *args):
        pass


class TestMCPRemote(unittest.TestCase):
    """Batería de pruebas funcionales y de seguridad para MCP remoto."""

    @classmethod
    def setUpClass(cls):
        # 1. Backend simulado en puerto efímero
        cls.backend_server = ThreadingHTTPServer(("127.0.0.1", 0), BackendFalsoMCP)
        cls.backend_port = cls.backend_server.server_address[1]
        cls.backend_url = f"http://127.0.0.1:{cls.backend_port}"
        cls.thread_backend = threading.Thread(target=cls.backend_server.serve_forever, daemon=True)
        cls.thread_backend.start()

        # 2. Configuración de credenciales de prueba
        cls.tmp_dir = tempfile.TemporaryDirectory()
        cls.tokens_file = Path(cls.tmp_dir.name) / "tokens.json"
        config_data = {
            "version": 1,
            "projects": {
                "proyecto-alpha": {
                    "token_sha256": HASH_ALPHA,
                    "revoked": False,
                    "scopes": [
                        "infer:text", "infer:vision", "infer:audio",
                        "speech:synthesize", "infer:video", "turn:stream",
                    ],
                    "rate_limit": {
                        "requests_per_minute": 600,
                        "burst": 50,
                        "max_concurrent": 5,
                        "max_queue": 10,
                        "queue_timeout_seconds": 5.0,
                    },
                },
                "proyecto-beta": {
                    "token_sha256": HASH_BETA,
                    "revoked": False,
                    "scopes": ["infer:text"],  # Scopes limitados para pruebas negativas
                    "rate_limit": {
                        "requests_per_minute": 300,
                        "burst": 30,
                        "max_concurrent": 2,
                        "max_queue": 5,
                        "queue_timeout_seconds": 5.0,
                    },
                },
            },
        }
        cls.tokens_file.write_text(json.dumps(config_data), encoding="utf-8")
        cls.registry = TokenRegistry(cls.tokens_file)
        cls.dispatcher = FairQueueDispatcher()

        # 3. Gateway configurado con MCP remoto activo
        cls.gateway_server = build_server(
            ("127.0.0.1", 0),
            backend=cls.backend_url,
            auth_enabled=True,
            tokens_registry=cls.registry,
            dispatcher=cls.dispatcher,
        )
        cls.gateway_server.tts_runner = cls._mock_tts_runner
        cls.gateway_server.probe_runner = cls._mock_probe_runner

        cls.gateway_port = cls.gateway_server.server_address[1]
        cls.gateway_url = f"http://127.0.0.1:{cls.gateway_port}"
        cls.thread_gw = threading.Thread(target=cls.gateway_server.serve_forever, daemon=True)
        cls.thread_gw.start()

    @classmethod
    def tearDownClass(cls):
        cls.gateway_server.shutdown()
        cls.gateway_server.server_close()
        cls.backend_server.shutdown()
        cls.backend_server.server_close()
        cls.tmp_dir.cleanup()

    @staticmethod
    def _mock_tts_runner(argv, prompt_path, wav_path, env):
        # Produce un WAV PCM 16kHz sintético válido (44 bytes cabecera + samples)
        Path(wav_path).write_bytes(
            b"RIFF\x2c\x00\x00\x00WAVEfmt \x10\x00\x00\x00"
            b"\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00"
            b"data\x08\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        )

    @staticmethod
    def _mock_probe_runner(datos):
        # Valida que tenga al menos ftyp
        if len(datos) < 8 or datos[4:8] != b"ftyp":
            from gateway_core import _error
            _error(400, "invalid_video", "caja ftyp ausente")

    def _peticion_post(self, body_dict, token=TOKEN_ALPHA, project="proyecto-alpha", extra_headers=None):
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "X-Project-ID": project,
        }
        if extra_headers:
            headers.update(extra_headers)

        data = json.dumps(body_dict).encode("utf-8")
        req = urllib.request.Request(f"{self.gateway_url}/mcp", data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                headers_out = dict(resp.headers)
                return resp.status, json.loads(resp.read().decode("utf-8")), headers_out
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8")), dict(exc.headers)

    def test_01_mcp_get_sse_channel(self):
        """Verifica canal SSE en GET /mcp y rechazo sin cabecera Accept apropiada."""
        # 1. Petición correcta con text/event-stream
        req = urllib.request.Request(
            f"{self.gateway_url}/mcp",
            headers={
                "Accept": "text/event-stream",
                "Authorization": f"Bearer {TOKEN_ALPHA}",
                "X-Project-ID": "proyecto-alpha",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/event-stream", resp.headers.get("Content-Type", ""))
            linea = resp.readline().decode("utf-8")
            self.assertTrue(linea.startswith("event: mcp.ready"))

        # 2. Petición incorrecta sin Accept
        req_bad = urllib.request.Request(
            f"{self.gateway_url}/mcp",
            headers={
                "Authorization": f"Bearer {TOKEN_ALPHA}",
                "X-Project-ID": "proyecto-alpha",
            },
            method="GET",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req_bad, timeout=5)
        self.assertEqual(ctx.exception.code, 400)

    def test_02_mcp_initialize_and_session(self):
        """Verifica negociación de protocolo initialize y emisión de Mcp-Session-Id."""
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        }
        status, res, headers = self._peticion_post(body)
        self.assertEqual(status, 200)
        self.assertEqual(res.get("jsonrpc"), "2.0")
        self.assertEqual(res.get("id"), 1)
        result = res.get("result", {})
        self.assertEqual(result.get("protocolVersion"), "2025-06-18")
        self.assertIn("tools", result.get("capabilities", {}))
        self.assertIn("Mcp-Session-Id", headers)

    def test_03_mcp_tools_list_omnimodal(self):
        """Verifica catálogo completo de 8 herramientas omnimodales en tools/list."""
        body = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        status, res, _ = self._peticion_post(body)
        self.assertEqual(status, 200)
        tools = res.get("result", {}).get("tools", [])
        tool_names = {t["name"] for t in tools}
        esperadas = {
            "health", "capabilities", "infer_text", "infer_vision",
            "infer_audio", "synthesize_speech", "infer_video", "conversational_turn",
        }
        self.assertEqual(esperadas, tool_names)

    def test_04_mcp_tools_call_health_and_capabilities(self):
        """Verifica invocación a health y capabilities."""
        # Health
        body_health = {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "health", "arguments": {}},
        }
        status, res, _ = self._peticion_post(body_health)
        self.assertEqual(status, 200)
        data = json.loads(res["result"]["content"][0]["text"])
        self.assertEqual(data.get("status"), "healthy")
        self.assertTrue(data.get("capabilities", {}).get("video"))

        # Capabilities
        body_cap = {
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "capabilities", "arguments": {}},
        }
        status, res, _ = self._peticion_post(body_cap)
        self.assertEqual(status, 200)
        data_cap = json.loads(res["result"]["content"][0]["text"])
        self.assertIn("entrada", data_cap)

    def test_05_mcp_tools_call_infer_text_plain_and_schema(self):
        """Verifica infer_text con texto plano y con validación de schema v2-ext."""
        # 1. Texto plano
        body_text = {
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {"name": "infer_text", "arguments": {"prompt": "Hola mundo"}},
        }
        status, res, _ = self._peticion_post(body_text)
        self.assertEqual(status, 200)
        data = json.loads(res["result"]["content"][0]["text"])
        self.assertIn("Eco LFM3", data.get("text", ""))

        # 2. Con Schema válido
        schema = {
            "type": "object",
            "properties": {
                "resultado": {"type": "string"},
                "valor": {"type": "integer"},
            },
            "required": ["resultado", "valor"],
            "additionalProperties": False,
        }
        body_schema = {
            "jsonrpc": "2.0", "id": 6, "method": "tools/call",
            "params": {"name": "infer_text", "arguments": {"prompt": "Dame JSON", "schema": schema}},
        }
        status, res, _ = self._peticion_post(body_schema)
        self.assertEqual(status, 200)
        data_sc = json.loads(res["result"]["content"][0]["text"])
        self.assertTrue(data_sc.get("validated"))

        # 3. Con Schema y modelo corrupto -> salida_invalida
        body_corrupto = {
            "jsonrpc": "2.0", "id": 7, "method": "tools/call",
            "params": {"name": "infer_text", "arguments": {"prompt": "Dame corrupto", "schema": schema}},
        }
        status, res, _ = self._peticion_post(body_corrupto)
        self.assertEqual(status, 200)
        self.assertTrue(res["result"]["isError"])
        err = json.loads(res["result"]["content"][0]["text"])
        self.assertEqual(err.get("error"), "salida_invalida")

    def test_06_mcp_tools_call_infer_vision_and_anti_ssrf(self):
        """Verifica infer_vision y contención estricta de egreso anti-SSRF."""
        # 1. Imagen PNG válida en base64
        png_magic = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        png_b64 = base64.b64encode(png_magic).decode("ascii")
        body_vis = {
            "jsonrpc": "2.0", "id": 8, "method": "tools/call",
            "params": {
                "name": "infer_vision",
                "arguments": {"prompt": "Qué ves", "image_base64": png_b64},
            },
        }
        status, res, _ = self._peticion_post(body_vis)
        self.assertEqual(status, 200)
        self.assertFalse(res["result"]["isError"])

        # 2. Intento de SSRF con URL externa
        body_ssrf = {
            "jsonrpc": "2.0", "id": 9, "method": "tools/call",
            "params": {
                "name": "infer_vision",
                "arguments": {"prompt": "Qué ves", "image_base64": "http://169.254.169.254/secret.png"},
            },
        }
        status, res, _ = self._peticion_post(body_ssrf)
        self.assertEqual(status, 200)
        self.assertTrue(res["result"]["isError"])
        err = json.loads(res["result"]["content"][0]["text"])
        self.assertIn("anti-SSRF", err.get("message", ""))

    def test_07_mcp_tools_call_infer_audio(self):
        """Verifica infer_audio con WAV válido y rechazo de audio inválido."""
        # WAV 16kHz válido
        wav_bytes = (
            b"RIFF\x2c\x00\x00\x00WAVEfmt \x10\x00\x00\x00"
            b"\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00"
            b"data\x08\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        )
        wav_b64 = base64.b64encode(wav_bytes).decode("ascii")
        body_aud = {
            "jsonrpc": "2.0", "id": 10, "method": "tools/call",
            "params": {"name": "infer_audio", "arguments": {"prompt": "Transcribe", "audio_base64": wav_b64}},
        }
        status, res, _ = self._peticion_post(body_aud)
        self.assertEqual(status, 200)
        self.assertFalse(res["result"]["isError"])

        # Audio corrupto
        body_bad = {
            "jsonrpc": "2.0", "id": 11, "method": "tools/call",
            "params": {"name": "infer_audio", "arguments": {"prompt": "Transcribe", "audio_base64": "bm90YXdhdg=="}},
        }
        status, res, _ = self._peticion_post(body_bad)
        self.assertEqual(status, 200)
        self.assertTrue(res["result"]["isError"])

    def test_08_mcp_tools_call_synthesize_speech_and_tts_busy(self):
        """Verifica synthesize_speech y exclusión mutua 503/tts_busy."""
        # 1. Síntesis normal
        body_tts = {
            "jsonrpc": "2.0", "id": 12, "method": "tools/call",
            "params": {"name": "synthesize_speech", "arguments": {"input": "Hola desde MCP"}},
        }
        status, res, _ = self._peticion_post(body_tts)
        self.assertEqual(status, 200)
        self.assertFalse(res["result"]["isError"])
        data = json.loads(res["result"]["content"][0]["text"])
        self.assertEqual(data.get("format"), "wav")
        self.assertTrue(len(data.get("audio_base64", "")) > 10)

        # 2. Exclusión mutua (cerrojo ocupado artificialmente)
        LOCK_TTS.acquire()
        try:
            status, res_busy, _ = self._peticion_post(body_tts)
            self.assertEqual(status, 200)
            self.assertTrue(res_busy["result"]["isError"])
            err = json.loads(res_busy["result"]["content"][0]["text"])
            self.assertEqual(err.get("error"), "tts_busy")
        finally:
            LOCK_TTS.release()

    def test_09_mcp_tools_call_infer_video(self):
        """Verifica infer_video con MP4 sintético y comprobación de ftyp."""
        mp4_sim = b"\x00\x00\x00\x20ftypmp42\x00\x00\x00\x00isommp42" + b"\x00" * 32
        mp4_b64 = base64.b64encode(mp4_sim).decode("ascii")
        body_vid = {
            "jsonrpc": "2.0", "id": 13, "method": "tools/call",
            "params": {"name": "infer_video", "arguments": {"prompt": "Describe video", "video_base64": mp4_b64}},
        }
        status, res, _ = self._peticion_post(body_vid)
        self.assertEqual(status, 200)
        self.assertFalse(res["result"]["isError"])

    def test_10_mcp_tools_call_conversational_turn(self):
        """Verifica conversational_turn con historial multi-turno y síntesis de voz."""
        body_turn = {
            "jsonrpc": "2.0", "id": 14, "method": "tools/call",
            "params": {
                "name": "conversational_turn",
                "arguments": {
                    "messages": [
                        {"role": "user", "content": "Hola"},
                        {"role": "assistant", "content": "Hola, ¿en qué te ayudo?"},
                        {"role": "user", "content": "Dime un chiste"},
                    ],
                    "synthesize_voice": True,
                },
            },
        }
        status, res, _ = self._peticion_post(body_turn)
        self.assertEqual(status, 200)
        self.assertFalse(res["result"]["isError"])
        data = json.loads(res["result"]["content"][0]["text"])
        self.assertIn("audio_base64", data)

    def test_11_mcp_auth_and_scope_failures(self):
        """Verifica rechazos de autenticación y de scopes no autorizados."""
        body_ping = {"jsonrpc": "2.0", "id": 15, "method": "ping", "params": {}}

        # 1. Falta Authorization
        req_no_auth = urllib.request.Request(
            f"{self.gateway_url}/mcp",
            data=json.dumps(body_ping).encode(),
            headers={"Content-Type": "application/json", "X-Project-ID": "proyecto-alpha"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req_no_auth)
        self.assertEqual(ctx.exception.code, 401)

        # 2. Mismatch proyecto-token
        status, res, _ = self._peticion_post(body_ping, token=TOKEN_ALPHA, project="proyecto-beta")
        self.assertEqual(status, 403)

        # 3. Scope insuficiente: proyecto-beta solo tiene infer:text, pide synthesize_speech
        body_tts = {
            "jsonrpc": "2.0", "id": 16, "method": "tools/call",
            "params": {"name": "synthesize_speech", "arguments": {"input": "Prueba"}},
        }
        status, res, _ = self._peticion_post(body_tts, token=TOKEN_BETA, project="proyecto-beta")
        self.assertEqual(status, 200)
        self.assertTrue(res["result"]["isError"])
        err = json.loads(res["result"]["content"][0]["text"])
        self.assertEqual(err.get("error"), "insufficient_scope")

    def test_12_mcp_session_isolation(self):
        """Verifica que una sesión creada por proyecto-alpha es rechazada si la usa proyecto-beta."""
        # 1. Crear sesión en proyecto-alpha
        body_init = {
            "jsonrpc": "2.0", "id": 17, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        }
        status, res, headers = self._peticion_post(body_init, token=TOKEN_ALPHA, project="proyecto-alpha")
        self.assertEqual(status, 200)
        sid = headers.get("Mcp-Session-Id")
        self.assertIsNotNone(sid)

        # 2. Intentar reutilizar esa sesión desde proyecto-beta -> 403 project_mismatch
        body_list = {"jsonrpc": "2.0", "id": 18, "method": "tools/list", "params": {}}
        status, res_mismatch, _ = self._peticion_post(
            body_list, token=TOKEN_BETA, project="proyecto-beta", extra_headers={"Mcp-Session-Id": sid}
        )
        self.assertEqual(status, 403)

    def test_13_mcp_synthesize_voice_rechazada_en_frontera(self):
        """Voz fija (issue #2): `voice` se rechaza antes del gateway."""
        body = {
            "jsonrpc": "2.0", "id": 19, "method": "tools/call",
            "params": {"name": "synthesize_speech",
                       "arguments": {"input": "Hola", "voice": "otra"}},
        }
        status, res, _ = self._peticion_post(body)
        self.assertEqual(status, 200)
        self.assertTrue(res["result"]["isError"])
        err = json.loads(res["result"]["content"][0]["text"])
        self.assertEqual(err.get("error"), "invalid_payload")
        self.assertIn("voice", err.get("message", ""))
        self.assertIn("campos no declarados", err.get("message", ""))

    def test_14_mcp_synthesize_speed_rechazado_en_frontera(self):
        """Voz fija (issue #2): `speed` se rechaza antes del gateway."""
        body = {
            "jsonrpc": "2.0", "id": 20, "method": "tools/call",
            "params": {"name": "synthesize_speech",
                       "arguments": {"input": "Hola", "speed": 1.5}},
        }
        status, res, _ = self._peticion_post(body)
        self.assertEqual(status, 200)
        self.assertTrue(res["result"]["isError"])
        err = json.loads(res["result"]["content"][0]["text"])
        self.assertEqual(err.get("error"), "invalid_payload")
        self.assertIn("speed", err.get("message", ""))
        self.assertIn("campos no declarados", err.get("message", ""))

    def test_15_mcp_tools_list_catalogo_voz_fija(self):
        """Voz fija (issue #2): el catálogo remoto no anuncia voice ni speed."""
        body = {"jsonrpc": "2.0", "id": 21, "method": "tools/list", "params": {}}
        status, res, _ = self._peticion_post(body)
        self.assertEqual(status, 200)
        tts = next(t for t in res["result"]["tools"]
                   if t["name"] == "synthesize_speech")
        self.assertNotIn("voice", tts["inputSchema"]["properties"])
        self.assertNotIn("speed", tts["inputSchema"]["properties"])


WAV_SINTETICO_VALIDO = (
    b"RIFF\x2c\x00\x00\x00WAVEfmt \x10\x00\x00\x00"
    b"\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00"
    b"data\x08\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
)


class RunnerTTSFalso:
    """Runner de TTS que cuenta llamadas y produce un WAV sintético válido."""

    def __init__(self):
        self.llamadas = 0
        self.ultimo_texto = None

    def __call__(self, argv, prompt_path, wav_path, env):
        self.llamadas += 1
        self.ultimo_texto = Path(prompt_path).read_text(encoding="utf-8")
        Path(wav_path).write_bytes(WAV_SINTETICO_VALIDO)


class HttpHandlerFalso:
    """Sustituto mínimo del http_handler para handle_post sin sockets."""

    def __init__(self):
        self.headers = {}
        self.respuestas = []

    def _json(self, status, cuerpo, extra=None):
        self.respuestas.append((status, json.loads(cuerpo.decode("utf-8"))))


class VozFijaRemotoFrontera(unittest.TestCase):
    """Voz fija en MCP remoto (issue #2, decisión del Operador 2026-11-07).

    Propiedades en frontera, sin sockets: rechazo de `voice` y `speed`
    antes del gateway, respuesta sin atribución, caso válido conservado,
    catálogo cerrado y concordancia documental SPEC↔contrato↔catálogo.
    """

    def setUp(self):
        self.runner = RunnerTTSFalso()
        self.handler = MCPRemoteHandler(
            backend_url="http://127.0.0.1:9", tts_runner=self.runner
        )

    def test_voice_rechazada_antes_del_gateway(self):
        res = self.handler._tool_synthesize_speech(
            {"input": "Hola", "voice": "otra"})
        self.assertTrue(res["isError"])
        detalle = json.loads(res["content"][0]["text"])
        self.assertEqual(detalle["error"], "invalid_payload")
        self.assertIn("voice", detalle["message"])
        self.assertIn("campos no declarados", detalle["message"])
        self.assertEqual(self.runner.llamadas, 0)

    def test_speed_rechazado_antes_del_gateway(self):
        res = self.handler._tool_synthesize_speech(
            {"input": "Hola", "speed": 1.5})
        self.assertTrue(res["isError"])
        detalle = json.loads(res["content"][0]["text"])
        self.assertEqual(detalle["error"], "invalid_payload")
        self.assertIn("speed", detalle["message"])
        self.assertIn("campos no declarados", detalle["message"])
        self.assertEqual(self.runner.llamadas, 0)

    def test_respuesta_exitosa_sin_atribucion(self):
        res = self.handler._tool_synthesize_speech({"input": "Hola mundo"})
        self.assertFalse(res["isError"])
        dato = json.loads(res["content"][0]["text"])
        self.assertNotIn("voice", dato)
        self.assertNotIn("speed", dato)
        self.assertEqual(dato["format"], "wav")
        self.assertEqual(dato["chars"], 10)
        self.assertEqual(base64.b64decode(dato["audio_base64"]),
                         WAV_SINTETICO_VALIDO)
        self.assertEqual(self.runner.llamadas, 1)
        self.assertEqual(self.runner.ultimo_texto, "Hola mundo")

    def test_caso_valido_conservado_campos_exactos(self):
        res = self.handler._tool_synthesize_speech({"input": "Hola"})
        self.assertFalse(res["isError"])
        dato = json.loads(res["content"][0]["text"])
        self.assertEqual(
            set(dato), {"audio_base64", "format", "chars", "duration_est_s"})

    def test_catalogo_cerrado_en_tools_list(self):
        fake = HttpHandlerFalso()
        self.handler.handle_post(
            fake, None,
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        status, resp = fake.respuestas[0]
        self.assertEqual(status, 200)
        tts = next(t for t in resp["result"]["tools"]
                   if t["name"] == "synthesize_speech")
        self.assertEqual(set(tts["inputSchema"]["properties"]),
                         {"input", "response_format"})
        self.assertFalse(tts["inputSchema"]["additionalProperties"])

    def test_concordancia_documental_spec_contrato_catalogo(self):
        spec = (RAIZ / "docs" / "specs" / "SPEC-i1-vm-mcp-v2.md").read_text(
            encoding="utf-8")
        spec3 = (RAIZ / "docs" / "specs" / "SPEC-i3-mcp-remote.md").read_text(
            encoding="utf-8")
        contrato = (RAIZ / "docs" / "contracts" / "mcp-tools-v2.md").read_text(
            encoding="utf-8")
        self.assertNotRegex(spec, r"voice: string")
        self.assertNotRegex(spec, r"speed: number")
        self.assertIn("voz fija", spec.lower())
        self.assertIn("2026-11-07", spec)
        self.assertIn("Voz fija y migración", contrato)
        self.assertIn("2026-11-07", contrato)
        tts = next(t for t in TOOLS_REMOTE
                   if t["name"] == "synthesize_speech")
        self.assertNotIn("voice", tts["inputSchema"]["properties"])
        self.assertNotIn("speed", tts["inputSchema"]["properties"])
        # SPEC-i3 §4.6: voz fija declarada con procedencia y remisión al
        # contrato (issue #2, decisión del Operador 2026-11-07). Sin
        # declaraciones de voice/speed: ni argumento (`voice`) ni campo de
        # salida ("voice"); la prosa de rechazo sí puede nombrarlos.
        seccion = spec3.split("### 4.6 `synthesize_speech`", 1)[1]
        seccion = seccion.split("### 4.7", 1)[0]
        self.assertNotRegex(seccion, r"`voice`")
        self.assertNotRegex(seccion, r"`speed`")
        self.assertNotRegex(seccion, r'"voice"')
        self.assertNotRegex(seccion, r'"speed"')
        self.assertIn("voz fija", seccion.lower())
        self.assertIn("2026-11-07", seccion)
        self.assertIn("Voz fija y migración", seccion)
        # El contrato no declara voice/speed ni en argumentos ni en salida
        # de synthesize_speech (sólo la sección de migración los menciona).
        args_seg = contrato.split("arguments.synthesize_speech:", 1)[1]
        args_seg = args_seg.split("arguments.", 1)[0]
        salida_seg = contrato.split("synthesize_speech ->", 1)[1]
        salida_seg = salida_seg.split("infer_video ->", 1)[0]
        self.assertNotIn("voice", args_seg)
        self.assertNotIn("speed", args_seg)
        self.assertNotIn("voice", salida_seg)
        self.assertNotIn("speed", salida_seg)
        # Esquemas de synthesize_speech idénticos en ambos catálogos
        # (stdio v2 y remoto), cerrados a los campos declarados.
        tts_stdio = next(t for t in TOOLS
                         if t["name"] == "synthesize_speech")
        self.assertEqual(tts_stdio["inputSchema"], tts["inputSchema"])
        for esquema in (tts["inputSchema"], tts_stdio["inputSchema"]):
            self.assertEqual(set(esquema["properties"]),
                             {"input", "response_format"})
            self.assertFalse(esquema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
