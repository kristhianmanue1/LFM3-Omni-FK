#!/usr/bin/env python3
"""Tests del servidor MCP stdio v2 contra SPEC-i1-vm y el CONTRATO mcp-tools v2.

Verifica:
1. Handshake, sesiones e inicialización.
2. Listado y esquemas de las 6 herramientas omnimodales.
3. Salud unificada con puertos 8092 y 8091 y capacidades.
4. Inferencia de texto con y sin dialecto schema v2-ext.
5. Inferencia de visión (PNG/JPEG), audio (WAV/MP3/FLAC) y video (MP4).
6. Síntesis de voz y compartición de cerrojo TTS 503 (mutex ocupado).
7. Prevalidación fail-closed de frontera con gateway_core.

Uso: python3 -m unittest tests.test_mcp_server_v2 -v
"""

import base64
import json
import struct
import subprocess
import sys
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import mcp_server_v2 as mcp2  # noqa: E402
from tests.test_gateway_i1 import GatewayBase, _BackendFalso


def _req(metodo, params=None, id_=1):
    msg = {"jsonrpc": "2.0", "id": id_, "method": metodo}
    if params is not None:
        msg["params"] = params
    resp = mcp2.procesar(json.dumps(msg))
    return json.loads(resp) if resp is not None else None


def _init():
    mcp2.INICIALIZADO = False
    _req("initialize", {"protocolVersion": "2025-06-18"})


def _png_minimo():
    ancho = alto = 8
    bruto = b"".join(b"\x00" + b"\xff\x00\x00" * ancho for _ in range(alto))

    def trozo(tipo, datos):
        cuerpo = tipo + datos
        crc = zlib.crc32(cuerpo) & 0xFFFFFFFF
        return struct.pack(">I", len(datos)) + cuerpo + struct.pack(">I", crc)

    return (
        b"\x89PNG\r\n\x1a\n"
        + trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
        + trozo(b"IDAT", zlib.compress(bruto))
        + trozo(b"IEND", b"")
    )


def _wav_minimo():
    # WAV PCM 16-bit 1 canal 16000 Hz, 100 muestras
    n_muestras = 100
    datos_pcm = b"\x00\x00" * n_muestras
    longitud_data = len(datos_pcm)
    longitud_riff = 36 + longitud_data
    fmt_chunk = struct.pack("<4sIHHIIHH", b"fmt ", 16, 1, 1, 16000, 32000, 2, 16)
    data_header = struct.pack("<4sI", b"data", longitud_data)
    riff_header = struct.pack("<4sI4s", b"RIFF", longitud_riff, b"WAVE")
    return riff_header + fmt_chunk + data_header + datos_pcm


def _mp4_minimo():
    # MP4 sintético mínimo con caja ftyp válida
    longitud = 20
    tipo = b"ftyp"
    major = b"isom"
    minor = b"\x00\x00\x02\x00"
    compat = b"isom"
    return struct.pack(">I4s4s4s4s", longitud, tipo, major, minor, compat)


class HandshakeV2(unittest.TestCase):
    """Handshake y ciclo de vida de sesión MCP v2."""

    def setUp(self):
        mcp2.INICIALIZADO = False

    def test_initialize_valido(self):
        resp = _req("initialize", {"protocolVersion": "2025-06-18"})
        res = resp.get("result", {})
        self.assertEqual(res.get("protocolVersion"), "2025-06-18")
        self.assertEqual(res.get("serverInfo", {}).get("name"), "lfm3-omni-mcp-v2")
        self.assertEqual(res.get("serverInfo", {}).get("version"), "0.2.0")

    def test_metodo_antes_de_initialize_rechazado_32002(self):
        resp = _req("tools/list")
        self.assertEqual(resp.get("error", {}).get("code"), -32002)

    def test_version_no_soportada_negocia_default(self):
        resp = _req("initialize", {"protocolVersion": "1999-01-01"})
        self.assertEqual(resp.get("result", {}).get("protocolVersion"), "2025-06-18")

    def test_notificacion_sin_respuesta(self):
        msg = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        resp = mcp2.procesar(json.dumps(msg))
        self.assertIsNone(resp)

    def test_tools_list_seis_herramientas(self):
        _init()
        resp = _req("tools/list")
        herramientas = resp.get("result", {}).get("tools", [])
        nombres = [t["name"] for t in herramientas]
        self.assertEqual(
            nombres,
            [
                "health",
                "infer_text",
                "infer_vision",
                "infer_audio",
                "synthesize_speech",
                "infer_video",
            ],
        )


class HealthV2(unittest.TestCase):
    """Salud unificada en MCP v2."""

    def setUp(self):
        _init()

    def test_health_con_arguments_rechazado(self):
        resp = _req("tools/call", {"name": "health", "arguments": {"extra": 1}})
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("arguments inválidos", resp["result"]["content"][0]["text"])

    @patch("mcp_server_v2._http_gateway")
    def test_health_gateway_up(self, mock_http):
        mock_http.side_effect = [
            (200, {"status": "ok"}),
            (200, {"entrada": ["texto", "imagen", "audio", "video"], "streaming": True}),
        ]
        resp = _req("tools/call", {"name": "health", "arguments": {}})
        self.assertFalse(resp["result"]["isError"])
        dato = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(dato["state"], "up")
        self.assertEqual(dato["gateway_port"], 8092)
        self.assertEqual(dato["backend_port"], 8091)
        self.assertIn("entrada", dato["capabilities"])

    @patch("mcp_server_v2._http_gateway")
    def test_health_gateway_down(self, mock_http):
        mock_http.side_effect = ConnectionError("conexión rechazada")
        resp = _req("tools/call", {"name": "health", "arguments": {}})
        self.assertFalse(resp["result"]["isError"])
        dato = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(dato["state"], "down")
        self.assertEqual(dato["capabilities"], {})


class InferTextV2(unittest.TestCase):
    """Inferencia de texto con schema v2-ext."""

    def setUp(self):
        _init()

    def test_campos_extra_rechazados(self):
        resp = _req("tools/call", {"name": "infer_text",
                                   "arguments": {"prompt": "hola", "foo": 1}})
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("campos no declarados", resp["result"]["content"][0]["text"])

    def test_prompt_invalido_rechazado(self):
        resp = _req("tools/call", {"name": "infer_text", "arguments": {"prompt": ""}})
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("prompt debe ser string", resp["result"]["content"][0]["text"])

    def test_schema_invalido_rechazado_en_frontera(self):
        # Schema con profundidad > 1 debe ser rechazado antes de llamar al gateway
        schema_profundo = {
            "type": "object",
            "properties": {
                "sub": {
                    "type": "object",
                    "properties": {
                        "sub2": {"type": "object", "properties": {"k": {"type": "string"}}}
                    },
                }
            },
        }
        resp = _req(
            "tools/call",
            {"name": "infer_text", "arguments": {"prompt": "hola", "schema": schema_profundo}},
        )
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("arguments inválidos", resp["result"]["content"][0]["text"])

    @patch("mcp_server_v2._http_gateway")
    def test_infer_text_sin_schema_exitoso(self, mock_http):
        mock_http.return_value = (
            200,
            {
                "choices": [{"message": {"content": "Respuesta texto"}}],
                "usage": {"total_tokens": 15},
            },
        )
        resp = _req("tools/call", {"name": "infer_text", "arguments": {"prompt": "Hola"}})
        self.assertFalse(resp["result"]["isError"])
        dato = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(dato["text"], "Respuesta texto")
        self.assertFalse(dato["validated"])
        self.assertEqual(dato["usage"]["total_tokens"], 15)

    @patch("mcp_server_v2._http_gateway")
    def test_infer_text_con_schema_v2_ext_exitoso(self, mock_http):
        schema = {
            "type": "object",
            "properties": {
                "etiquetas": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
                "puntuacion": {"type": "integer", "minimum": 0, "maximum": 10},
            },
            "required": ["etiquetas", "puntuacion"],
        }
        mock_http.return_value = (
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"etiquetas": ["a", "b"], "puntuacion": 8}
                            )
                        }
                    }
                ],
                "usage": {"total_tokens": 25},
            },
        )
        resp = _req(
            "tools/call",
            {"name": "infer_text", "arguments": {"prompt": "Evalúa", "schema": schema}},
        )
        self.assertFalse(resp["result"]["isError"])
        dato = json.loads(resp["result"]["content"][0]["text"])
        self.assertTrue(dato["validated"])
        self.assertIn('"puntuacion": 8', dato["text"])

    @patch("mcp_server_v2._http_gateway")
    def test_infer_text_salida_que_viola_schema_es_salida_invalida(self, mock_http):
        schema = {
            "type": "object",
            "properties": {"puntuacion": {"type": "integer", "maximum": 10}},
            "required": ["puntuacion"],
        }
        # El modelo responde puntuacion fuera de rango (15 > 10)
        mock_http.return_value = (
            200,
            {
                "choices": [
                    {"message": {"content": json.dumps({"puntuacion": 15})}}
                ],
                "usage": {"total_tokens": 10},
            },
        )
        resp = _req(
            "tools/call",
            {"name": "infer_text", "arguments": {"prompt": "Evalúa", "schema": schema}},
        )
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("salida_invalida", resp["result"]["content"][0]["text"])

    def test_max_tokens_booleano_cero_y_4097_rechazados(self):
        for invalido in (True, False, 0, 4097, -1, "512"):
            with self.subTest(invalido=invalido):
                resp = _req(
                    "tools/call",
                    {"name": "infer_text", "arguments": {"prompt": "x", "max_tokens": invalido}},
                )
                self.assertTrue(resp["result"]["isError"])
                self.assertIn("max_tokens debe ser entero", resp["result"]["content"][0]["text"])

    @patch("mcp_server_v2._http_gateway")
    def test_max_tokens_default_512(self, mock_http):
        mock_http.return_value = (
            200,
            {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"total_tokens": 5},
            },
        )
        _req("tools/call", {"name": "infer_text", "arguments": {"prompt": "x"}})
        self.assertEqual(mock_http.call_args[0][2]["max_tokens"], 512)


class InferMultimodalV2(unittest.TestCase):
    """Visión, audio y video en MCP v2."""

    def setUp(self):
        _init()

    def test_infer_vision_imagen_invalida_rechazada_en_frontera(self):
        resp = _req(
            "tools/call",
            {"name": "infer_vision", "arguments": {"image_base64": "abc!", "prompt": "mira"}},
        )
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("no decodifica como base64", resp["result"]["content"][0]["text"])

    @patch("mcp_server_v2._http_gateway")
    def test_infer_vision_png_valido(self, mock_http):
        mock_http.return_value = (
            200,
            {
                "choices": [{"message": {"content": "Un píxel blanco"}}],
                "usage": {"total_tokens": 30},
            },
        )
        img_b64 = base64.b64encode(_png_minimo()).decode("ascii")
        resp = _req(
            "tools/call",
            {"name": "infer_vision", "arguments": {"image_base64": img_b64, "prompt": "describe"}},
        )
        self.assertFalse(resp["result"]["isError"])
        dato = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(dato["description"], "Un píxel blanco")

    def test_infer_audio_invalido_rechazado_en_frontera(self):
        # Audio que no es WAV/MP3/FLAC
        basura = base64.b64encode(b"NO_AUDIO_DATA_HERE").decode("ascii")
        resp = _req(
            "tools/call",
            {"name": "infer_audio", "arguments": {"audio_base64": basura, "prompt": "oye"}},
        )
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("formato no soportado", resp["result"]["content"][0]["text"])

    @patch("mcp_server_v2._http_gateway")
    def test_infer_audio_wav_valido(self, mock_http):
        mock_http.return_value = (
            200,
            {
                "choices": [{"message": {"content": "Audio transcrito"}}],
                "usage": {"total_tokens": 20},
            },
        )
        wav_b64 = base64.b64encode(_wav_minimo()).decode("ascii")
        resp = _req(
            "tools/call",
            {"name": "infer_audio", "arguments": {"audio_base64": wav_b64, "prompt": "transcribe"}},
        )
        self.assertFalse(resp["result"]["isError"])
        dato = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(dato["text"], "Audio transcrito")

    def test_infer_video_invalido_rechazado_en_frontera(self):
        basura = base64.b64encode(b"NO_MP4").decode("ascii")
        resp = _req(
            "tools/call",
            {"name": "infer_video", "arguments": {"video_base64": basura, "prompt": "mira"}},
        )
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("firma MP4/ftyp", resp["result"]["content"][0]["text"])

    @patch("mcp_server_v2._http_gateway")
    def test_infer_video_mp4_valido(self, mock_http):
        mock_http.return_value = (
            200,
            {
                "choices": [{"message": {"content": "Video con animación"}}],
                "usage": {"total_tokens": 40},
            },
        )
        mp4_b64 = base64.b64encode(_mp4_minimo()).decode("ascii")
        resp = _req(
            "tools/call",
            {"name": "infer_video", "arguments": {"video_base64": mp4_b64, "prompt": "analiza"}},
        )
        self.assertFalse(resp["result"]["isError"])
        dato = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(dato["description"], "Video con animación")

    @patch("mcp_server_v2._http_gateway")
    def test_max_tokens_default_1024_en_vision(self, mock_http):
        mock_http.return_value = (
            200,
            {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"total_tokens": 10},
            },
        )
        img_b64 = base64.b64encode(_png_minimo()).decode("ascii")
        _req("tools/call", {
            "name": "infer_vision",
            "arguments": {"image_base64": img_b64, "prompt": "mira"},
        })
        self.assertEqual(mock_http.call_args[0][2]["max_tokens"], 1024)


class SynthesizeSpeechV2(unittest.TestCase):
    """Síntesis de voz y compartición del cerrojo TTS 503."""

    def setUp(self):
        _init()

    def test_input_mas_de_600_caracteres_rechazado(self):
        texto_largo = "a" * 601
        resp = _req(
            "tools/call",
            {"name": "synthesize_speech", "arguments": {"input": texto_largo}},
        )
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("input debe ser string", resp["result"]["content"][0]["text"])

    def test_input_con_caracteres_de_control_rechazado(self):
        resp = _req(
            "tools/call",
            {"name": "synthesize_speech", "arguments": {"input": "hola\x00mundo"}},
        )
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("caracteres de control", resp["result"]["content"][0]["text"])

    def test_response_format_invalido_rechazado(self):
        resp = _req(
            "tools/call",
            {
                "name": "synthesize_speech",
                "arguments": {"input": "Hola", "response_format": "mp3"},
            },
        )
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("response_format sólo admite 'wav'",
                      resp["result"]["content"][0]["text"])

    @patch("mcp_server_v2._http_gateway")
    def test_synthesize_speech_exitoso(self, mock_http):
        audio_wav = _wav_minimo()
        mock_http.return_value = (200, audio_wav)
        resp = _req(
            "tools/call",
            {"name": "synthesize_speech", "arguments": {"input": "Hola mundo"}},
        )
        self.assertFalse(resp["result"]["isError"])
        dato = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(dato["format"], "wav")
        self.assertNotIn("voice", dato)
        self.assertNotIn("speed", dato)
        self.assertEqual(dato["chars"], 10)
        recuperado = base64.b64decode(dato["audio_base64"])
        self.assertEqual(recuperado, audio_wav)

    @patch("mcp_server_v2._http_gateway")
    def test_voice_rechazada_antes_gateway(self, mock_http):
        resp = _req("tools/call", {"name": "synthesize_speech",
                                   "arguments": {"input": "Hola", "voice": "otra"}})
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("voice", resp["result"]["content"][0]["text"])
        mock_http.assert_not_called()

    @patch("mcp_server_v2._http_gateway")
    def test_speed_rechazada_antes_gateway(self, mock_http):
        resp = _req("tools/call", {"name": "synthesize_speech",
                                   "arguments": {"input": "Hola", "speed": 1.5}})
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("speed", resp["result"]["content"][0]["text"])
        mock_http.assert_not_called()

    @patch("mcp_server_v2._http_gateway")
    def test_campo_desconocido_rechazado_antes_gateway(self, mock_http):
        resp = _req("tools/call", {"name": "synthesize_speech",
                                   "arguments": {"input": "Hola", "extra": 1}})
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("extra", resp["result"]["content"][0]["text"])
        mock_http.assert_not_called()

    @patch("mcp_server_v2._http_gateway")
    def test_wav_invalido_rechazado(self, mock_http):
        mock_http.return_value = (200, b"no es wav")
        resp = _req("tools/call", {"name": "synthesize_speech",
                                   "arguments": {"input": "Hola"}})
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("WAV", resp["result"]["content"][0]["text"])

    def test_tools_list_voz_fija(self):
        tool = next(t for t in _req("tools/list")["result"]["tools"]
                    if t["name"] == "synthesize_speech")
        self.assertNotIn("voice", tool["inputSchema"]["properties"])
        self.assertNotIn("speed", tool["inputSchema"]["properties"])
        self.assertFalse(tool["inputSchema"]["additionalProperties"])

    def test_proceso_rechaza_voice_y_speed_antes_backend(self):
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18"}},
            *({"jsonrpc": "2.0", "id": index, "method": "tools/call",
               "params": {"name": "synthesize_speech",
                          "arguments": {"input": "Hola", field: value}}}
              for index, field, value in ((2, "voice", "otra"),
                                          (3, "speed", 1.5))),
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "synthesize_speech",
                        "arguments": {"input": "Control"}}},
        ]
        code = (
            "import sys; sys.path.insert(0, 'src'); import mcp_server_v2 as m; "
            "m._http_gateway = lambda *a, **kw: "
            "(sys.stderr.write('BACKEND_CALLED\\n'), (200, b''))[1]; m.main()"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code], cwd=RAIZ,
            input="\n".join(json.dumps(req) for req in requests) + "\n",
            text=True, capture_output=True, timeout=10, check=True,
        )
        responses = [json.loads(line) for line in proc.stdout.splitlines()]
        self.assertEqual(len(responses), 4)
        for response, field in zip(responses[1:3], ("voice", "speed")):
            self.assertTrue(response["result"]["isError"])
            self.assertIn(field, response["result"]["content"][0]["text"])
        self.assertEqual(proc.stderr.count("BACKEND_CALLED"), 1)

    def test_gateway_tts_texto_fuera_argv_y_limpieza(self):
        from gateway_http import _sintetizar_wav
        observed = {}

        def runner(argv, prompt_path, wav_path, _env):
            observed["argv"] = argv
            observed["prompt_path"] = Path(prompt_path)
            observed["text"] = Path(prompt_path).read_text(encoding="utf-8")
            observed["mode"] = Path(prompt_path).stat().st_mode & 0o777
            Path(wav_path).write_bytes(_wav_minimo())

        result = _sintetizar_wav("Texto privado", runner=runner)
        self.assertEqual(result, _wav_minimo())
        self.assertEqual(observed["text"], "Texto privado")
        self.assertNotIn("Texto privado", observed["argv"])
        self.assertEqual(observed["mode"], 0o600)
        self.assertFalse(observed["prompt_path"].exists())

    @patch("mcp_server_v2._http_gateway")
    def test_synthesize_speech_cerrojo_ocupado_retorna_503_tts_busy(self, mock_http):
        mock_http.return_value = (503, b'{"error":{"message":"tts busy"}}')
        resp = _req(
            "tools/call",
            {"name": "synthesize_speech", "arguments": {"input": "Habla"}},
        )
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("tts_busy", resp["result"]["content"][0]["text"])
        self.assertIn("503 reintentable", resp["result"]["content"][0]["text"])


class ProtocoloRobustezV2(unittest.TestCase):
    """Robustez JSON-RPC y manejo de fallos generales."""

    def setUp(self):
        _init()

    def test_parse_error_32700(self):
        resp = json.loads(mcp2.procesar("no json"))
        self.assertEqual(resp["error"]["code"], -32700)

    def test_mensaje_no_objeto_32600(self):
        resp = json.loads(mcp2.procesar("[]"))
        self.assertEqual(resp["error"]["code"], -32600)

    def test_tool_desconocida_32602(self):
        resp = _req("tools/call", {"name": "herramienta_fantasma", "arguments": {}})
        self.assertEqual(resp["error"]["code"], -32602)

    def test_params_no_objeto_32600(self):
        resp = _req("tools/list", params=["invalido"])
        self.assertEqual(resp["error"]["code"], -32600)

    def test_metodo_desconocido_32601(self):
        resp = _req("metodo_inexistente")
        self.assertEqual(resp["error"]["code"], -32601)

    def test_surrogate_no_mata_el_bucle(self):
        surrogate = "\ud800"
        resp = mcp2.procesar(f'{{"jsonrpc":"2.0","id":1,"method":"{surrogate}"}}')
        self.assertIsNotNone(resp)
        self.assertIn("error", json.loads(resp))

    @patch("mcp_server_v2._http_gateway")
    def test_choices_vacio_es_salida_invalida(self, mock_http):
        mock_http.return_value = (200, {"choices": [], "usage": {}})
        resp = _req("tools/call", {"name": "infer_text", "arguments": {"prompt": "x"}})
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("salida_invalida", resp["result"]["content"][0]["text"])

    @patch("mcp_server_v2._http_gateway")
    def test_usage_ausente_es_salida_invalida(self, mock_http):
        mock_http.return_value = (
            200,
            {"choices": [{"message": {"content": "ok"}}]},
        )
        resp = _req("tools/call", {"name": "infer_text", "arguments": {"prompt": "x"}})
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("salida_invalida", resp["result"]["content"][0]["text"])


class McpGatewayLiveIntegration(GatewayBase):
    """Integración e2e de MCP v2 contra servidor gateway HTTP real."""

    def setUp(self):
        super().setUp()
        _init()
        self.orig_host = mcp2.GATEWAY_HOST
        self.orig_port = mcp2.GATEWAY_PORT
        self.orig_url = mcp2.GATEWAY_URL
        mcp2.GATEWAY_HOST = "127.0.0.1"
        mcp2.GATEWAY_PORT = self.port
        mcp2.GATEWAY_URL = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        mcp2.GATEWAY_HOST = self.orig_host
        mcp2.GATEWAY_PORT = self.orig_port
        mcp2.GATEWAY_URL = self.orig_url
        super().tearDown()

    def test_health_e2e_gateway_vivo(self):
        resp = _req("tools/call", {"name": "health", "arguments": {}})
        self.assertFalse(resp["result"]["isError"])
        dato = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(dato["state"], "up")
        self.assertEqual(dato["gateway_port"], self.port)
        self.assertIn("entrada", dato["capabilities"])

    def test_infer_text_e2e_gateway_vivo(self):
        _BackendFalso.canned = {
            "choices": [{"message": {"content": "Respuesta desde backend"}}],
            "usage": {"total_tokens": 12},
        }
        resp = _req("tools/call", {"name": "infer_text",
                                   "arguments": {"prompt": "Hola mundo"}})
        self.assertFalse(resp["result"]["isError"])
        dato = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(dato["text"], "Respuesta desde backend")
        self.assertFalse(dato["validated"])
        self.assertEqual(dato["usage"]["total_tokens"], 12)

    def test_infer_vision_e2e_gateway_vivo(self):
        _BackendFalso.canned = {
            "choices": [{"message": {"content": "Imagen procesada"}}],
            "usage": {"total_tokens": 20},
        }
        img_b64 = base64.b64encode(_png_minimo()).decode("ascii")
        resp = _req("tools/call", {
            "name": "infer_vision",
            "arguments": {"image_base64": img_b64, "prompt": "Analiza"},
        })
        self.assertFalse(resp["result"]["isError"])
        dato = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(dato["description"], "Imagen procesada")

    def test_synthesize_speech_503_cerrojo_tts_compartido_con_gateway(self):
        from gateway_http import LOCK_TTS
        # Adquirimos el cerrojo TTS en el proceso
        self.assertTrue(LOCK_TTS.acquire(blocking=False))
        try:
            resp = _req("tools/call", {
                "name": "synthesize_speech",
                "arguments": {"input": "Texto para hablar"},
            })
            self.assertTrue(resp["result"]["isError"])
            err_msg = resp["result"]["content"][0]["text"]
            self.assertIn("tts_busy", err_msg)
            self.assertIn("503 reintentable", err_msg)
        finally:
            LOCK_TTS.release()


if __name__ == "__main__":
    unittest.main()
