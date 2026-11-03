#!/usr/bin/env python3
"""Tests del servidor MCP contra SPEC-2 y el CONTRATO mcp-tools v1.

Cada test ejecuta un caso DADO/CUANDO/ENTONCES de SPEC-2 o un caso
borde de la ronda adversarial F3. Los tests de tools requieren el motor
vivo (bash run/serve.sh); los de validación y errores sustituyen _http,
así que corren sin motor.

Uso: python3 -m unittest tests.test_mcp_server -v
"""

import base64
import io
import json
import struct
import subprocess
import sys
import unittest
import urllib.error
import zlib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import mcp_server as mcp  # noqa: E402


def requerir(metodo, params=None, id_=1):
    msg = {"jsonrpc": "2.0", "id": id_, "method": metodo}
    if params is not None:
        msg["params"] = params
    return json.loads(mcp.procesar(json.dumps(msg)))


def inicializar():
    requerir("initialize", {"protocolVersion": "2025-06-18"})


def contenido_json(respuesta):
    cuerpo = respuesta["result"]
    assert not cuerpo.get("isError"), cuerpo
    return json.loads(cuerpo["content"][0]["text"])


def png_rojo():
    ancho = alto = 8
    bruto = b"".join(b"\x00" + b"\xff\x00\x00" * ancho for _ in range(alto))

    def trozo(tipo, datos):
        cuerpo = tipo + datos
        return struct.pack(">I", len(datos)) + cuerpo + struct.pack(">I", zlib.crc32(cuerpo))

    return base64.b64encode(
        b"\x89PNG\r\n\x1a\n"
        + trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
        + trozo(b"IDAT", zlib.compress(bruto))
        + trozo(b"IEND", b"")
    ).decode()


SCHEMA_REGISTRO = {"type": "object", "properties": {
    "nombre": {"type": "string"}, "edad": {"type": "integer"}},
    "required": ["nombre", "edad"]}


class Handshake(unittest.TestCase):
    """SPEC-2 caso 1: initialize responde capabilities y tres tools."""

    def setUp(self):
        mcp.INICIALIZADO = False

    def test_initialize(self):
        r = requerir("initialize", {"protocolVersion": "2025-06-18"})
        self.assertIn("tools", r["result"]["capabilities"])

    def test_tools_list_tres(self):
        inicializar()
        nombres = [t["name"] for t in requerir("tools/list")["result"]["tools"]]
        self.assertEqual(nombres, ["health", "infer_text", "infer_vision"])

    def test_metodo_desconocido(self):
        inicializar()
        r = requerir("salud/extraña")
        self.assertEqual(r["error"]["code"], -32601)

    def test_notificacion_sin_respuesta(self):
        inicializar()
        self.assertIsNone(mcp.procesar(json.dumps(
            {"jsonrpc": "2.0", "method": "notifications/initialized"})))

    def test_version_no_soportada_negocia_default(self):
        r = requerir("initialize", {"protocolVersion": "1999-01-01"})
        self.assertEqual(r["result"]["protocolVersion"], mcp.PROTO_DEFAULT)

    def test_tools_antes_de_initialize(self):
        r = requerir("tools/list", id_=9)
        self.assertEqual(r["error"]["code"], -32002)


class Validacion(unittest.TestCase):
    """Casos borde de la ronda adversarial F3, sin motor (http sustituido)."""

    def setUp(self):
        mcp.INICIALIZADO = True

    def _stub(self, cuerpo):
        self._original = mcp._http
        mcp._http = lambda *a, **k: (200, cuerpo)

    def _restore(self):
        mcp._http = self._original

    def test_prompt_8001_rechazado(self):
        r = requerir("tools/call", {"name": "infer_text",
                                    "arguments": {"prompt": "x" * 8001}})
        self.assertTrue(r["result"]["isError"])
        self.assertIn("1..8000", r["result"]["content"][0]["text"])

    def test_prompt_8000_aceptado(self):
        self._stub({"choices": [{"message": {"content": "ok"}}], "usage": {}})
        try:
            r = requerir("tools/call", {"name": "infer_text",
                                        "arguments": {"prompt": "x" * 8000}})
            self.assertFalse(r["result"]["isError"])
        finally:
            self._restore()

    def test_max_tokens_booleano_cero_y_4097(self):
        for malo in (True, 0, 4097, "64"):
            r = requerir("tools/call", {"name": "infer_text",
                                        "arguments": {"prompt": "x", "max_tokens": malo}})
            self.assertTrue(r["result"]["isError"], malo)

    def test_campo_no_declarado_rechazado_por_nombre(self):
        r = requerir("tools/call", {"name": "infer_text",
                                    "arguments": {"prompt": "x", "maxtokens": 10}})
        self.assertTrue(r["result"]["isError"])
        self.assertIn("maxtokens", r["result"]["content"][0]["text"])

    def test_schema_null_rechazado(self):
        r = requerir("tools/call", {"name": "infer_text",
                                    "arguments": {"prompt": "x", "schema": None}})
        self.assertTrue(r["result"]["isError"])

    def test_schema_con_claves_no_soportadas_rechazado(self):
        r = requerir("tools/call", {"name": "infer_text", "arguments": {
            "prompt": "x", "schema": {"type": "object", "pattern": ".*"}}})
        self.assertTrue(r["result"]["isError"])
        self.assertIn("no soportadas", r["result"]["content"][0]["text"])

    def test_salida_json_valido_pero_no_conforme(self):
        # BLOCKER de la ronda F3: JSON válido que viola el schema -> isError.
        self._stub({"choices": [{"message": {"content": '{"edad": "treinta y cuatro"}'}}],
                    "usage": {}})
        try:
            r = requerir("tools/call", {"name": "infer_text", "arguments": {
                "prompt": "registra", "schema": SCHEMA_REGISTRO}})
            self.assertTrue(r["result"]["isError"])
            self.assertIn("salida_invalida", r["result"]["content"][0]["text"])
        finally:
            self._restore()

    def test_usage_ausente_o_nulo_es_salida_invalida(self):
        for cuerpo in ({"choices": [{"message": {"content": "x"}}]},
                       {"choices": [{"message": {"content": "x"}}], "usage": None}):
            self._stub(cuerpo)
            try:
                r = requerir("tools/call", {"name": "infer_text",
                                            "arguments": {"prompt": "x"}})
                self.assertTrue(r["result"]["isError"], cuerpo)
                self.assertIn("salida_invalida", r["result"]["content"][0]["text"])
            finally:
                self._restore()

    def test_choices_vacio_es_salida_invalida(self):
        self._stub({"choices": [], "usage": {}})
        try:
            r = requerir("tools/call", {"name": "infer_text",
                                        "arguments": {"prompt": "x"}})
            self.assertTrue(r["result"]["isError"])
        finally:
            self._restore()

    def test_imagen_basura_rechazada_en_frontera(self):
        r = requerir("tools/call", {"name": "infer_vision", "arguments": {
            "image_base64": base64.b64encode(b"no es imagen").decode(),
            "prompt": "describe"}})
        self.assertTrue(r["result"]["isError"])
        self.assertIn("PNG o JPEG", r["result"]["content"][0]["text"])

    def test_imagen_no_base64_rechazada(self):
        r = requerir("tools/call", {"name": "infer_vision", "arguments": {
            "image_base64": "@@no-base64@@", "prompt": "describe"}})
        self.assertTrue(r["result"]["isError"])

    def test_health_con_arguments_rechazado(self):
        r = requerir("tools/call", {"name": "health", "arguments": {"x": 1}})
        self.assertTrue(r["result"]["isError"])

    def test_tool_desconocida_es_error_de_protocolo(self):
        r = requerir("tools/call", {"name": "clima"})
        self.assertEqual(r["error"]["code"], -32602)

    def test_surrogate_no_mata_el_bucle(self):
        salida = mcp.procesar(json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "t\ud800"}}))
        self.assertIsNotNone(salida)


def _httperror(code, cuerpo):
    return urllib.error.HTTPError(
        "http://x", code, "e", {}, io.BytesIO(json.dumps(cuerpo).encode()))


class ClasificacionHTTP(unittest.TestCase):
    """Ronda 2 (H3/M1/M5): clasificación de errores del motor bajo test."""

    def setUp(self):
        mcp.INICIALIZADO = True
        self._original = mcp._http

    def tearDown(self):
        mcp._http = self._original

    def _lanza(self, exc):
        def lanzador(*a, **k):
            raise exc
        mcp._http = lanzador

    def _llama_infer(self):
        return requerir("tools/call", {"name": "infer_text",
                                       "arguments": {"prompt": "x"}})

    def test_400_con_detalle_estructurado(self):
        self._lanza(_httperror(400, {"error": {"code": 400,
                                               "message": "campo imagen inválido"}}))
        r = self._llama_infer()
        texto = r["result"]["content"][0]["text"]
        self.assertIn("motor rechazó la entrada", texto)
        self.assertIn("campo imagen inválido", texto)

    def test_400_con_error_string(self):
        self._lanza(_httperror(400, {"error": "texto plano"}))
        r = self._llama_infer()
        self.assertIn("motor rechazó la entrada", r["result"]["content"][0]["text"])

    def test_400_con_error_no_dict_y_no_string(self):
        self._lanza(_httperror(400, {"error": 42}))
        r = self._llama_infer()
        self.assertIn("motor rechazó la entrada", r["result"]["content"][0]["text"])

    def test_503_es_reintentable(self):
        self._lanza(_httperror(503, {"error": {"message": "loading"}}))
        r = self._llama_infer()
        self.assertIn("motor cargando, reintentable", r["result"]["content"][0]["text"])

    def test_500_generico(self):
        self._lanza(_httperror(500, {}))
        r = self._llama_infer()
        self.assertIn("motor respondió 500", r["result"]["content"][0]["text"])

    def test_200_no_parseable_es_salida_invalida(self):
        self._lanza(json.JSONDecodeError("x", "y", 0))
        r = self._llama_infer()
        self.assertIn("salida_invalida", r["result"]["content"][0]["text"])

    def test_parse_error_32700(self):
        r = json.loads(mcp.procesar("no-json"))
        self.assertEqual(r["error"]["code"], -32700)

    def test_mensaje_no_objeto_32600(self):
        r = json.loads(mcp.procesar("[1,2,3]"))
        self.assertEqual(r["error"]["code"], -32600)

    def test_params_no_objeto_32600(self):
        r = json.loads(mcp.procesar(json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": 7})))
        self.assertEqual(r["error"]["code"], -32600)

    def test_schema_profundo_no_mata(self):
        schema = {}
        actual = schema
        for _ in range(300):
            actual["properties"] = {"p": {}}
            actual = actual["properties"]["p"]
        r = requerir("tools/call", {"name": "infer_text",
                                    "arguments": {"prompt": "x", "schema": schema}})
        self.assertTrue(r["result"].get("isError") or r.get("error"))

    def test_main_sobrevive_surrogate_e2e(self):
        linea = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                            "params": {"name": "t\ud800"}}) + "\n"
        p = subprocess.run(
            [sys.executable, str(RAIZ / "src" / "mcp_server.py")],
            input=linea, capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0)
        self.assertTrue(p.stdout.strip())


class ToolsConMotor(unittest.TestCase):
    """Requiere motor vivo (bash run/serve.sh)."""

    def setUp(self):
        inicializar()

    def test_health_up(self):
        datos = contenido_json(requerir("tools/call", {"name": "health"}))
        self.assertEqual(datos["state"], "up")
        self.assertEqual(datos["model"], "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M")
        self.assertEqual(datos["port"], 8091)

    def test_infer_text_con_schema(self):
        args = {"prompt": "Registra a Ana de 34 años según el esquema.",
                "schema": SCHEMA_REGISTRO}
        datos = contenido_json(requerir("tools/call", {"name": "infer_text", "arguments": args}))
        self.assertTrue(datos["validated"])
        self.assertEqual(json.loads(datos["text"]), {"nombre": "Ana", "edad": 34})

    def test_infer_text_sin_schema(self):
        args = {"prompt": "Responde con una sola palabra: ¿qué color tiene el cielo despejado de día?"}
        datos = contenido_json(requerir("tools/call", {"name": "infer_text", "arguments": args}))
        self.assertFalse(datos["validated"])
        self.assertIsInstance(datos["text"], str)
        self.assertTrue(len(datos["text"]) > 0)

    def test_infer_vision_png_rojo(self):
        args = {"image_base64": png_rojo(),
                "prompt": "¿De qué color es esta imagen? Responde con una sola palabra."}
        datos = contenido_json(requerir("tools/call", {"name": "infer_vision", "arguments": args}))
        texto = datos["description"].lower()
        self.assertTrue("rojo" in texto or "red" in texto, datos["description"])


class MotorCaido(unittest.TestCase):
    """SPEC-2 caso 6: motor abajo -> isError y proceso vivo. Sin motor."""

    def setUp(self):
        inicializar()
        self._url_original = mcp.MOTOR_URL
        mcp.MOTOR_URL = "http://127.0.0.1:1"

    def tearDown(self):
        mcp.MOTOR_URL = self._url_original

    def test_infer_text_motor_caido(self):
        r = requerir("tools/call", {"name": "infer_text",
                                    "arguments": {"prompt": "hola"}})
        self.assertTrue(r["result"].get("isError"))
        self.assertIn("motor", r["result"]["content"][0]["text"].lower())

    def test_health_reporta_down(self):
        datos = contenido_json(requerir("tools/call", {"name": "health"}))
        self.assertEqual(datos["state"], "down")


if __name__ == "__main__":
    unittest.main()
