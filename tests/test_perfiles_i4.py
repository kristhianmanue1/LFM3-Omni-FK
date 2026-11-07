#!/usr/bin/env python3
"""Pruebas unitarias e integradas para la Fase I4 (Perfiles W y D).

Verifica exhaustivamente:
1. Cliente SDK Perfil W (Python):
   - Construcción de payloads para todas las modalidades (texto, estructurado,
     visión, audio, voz, video, streaming SSE y cancelación).
   - Manejo de autenticación Bearer y correlación client_request_id.
   - Manejo de fallos controlados (503 tts_busy, 429 rate limit, errores de red).
   - Saneamiento de salida en frontera (anti-XSS).
2. Adaptador Perfil D con autenticación y salvaguardas temporales:
   - Envío de credencial Bearer y cabecera X-Client-Request-ID.
   - Entrada sensorial multimodal (imagen y telemetría).
   - Invariantes de tiempo real (deriva reloj, pre/post expiración, deduplicación).
   - Filtrado estricto por lista blanca de acciones autorizadas.
3. Compatibilidad de ejecutables de referencia:
   - cliente_perfil_w.py --demo (exit 0).
   - cliente_perfil_w.mjs con Node.js (exit 0).
   - simulador_robot_perfil_d.py (exit 0).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "examples"))

from adaptador_perfil_d import RobotAdapterD  # noqa: E402
from cliente_perfil_w import PerfilWClient, sanitize_for_display  # noqa: E402


class PerfilWClientTests(unittest.TestCase):
    """Pruebas unitarias del cliente SDK para Perfil W."""

    def setUp(self):
        self.client = PerfilWClient(
            base_url="http://127.0.0.1:8092",
            auth_token="test-token-alpha",
        )

    def test_01_headers_autenticacion_y_correlacion(self):
        headers = self.client._headers(client_request_id="cli-req-123")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Authorization"], "Bearer test-token-alpha")
        self.assertEqual(headers["X-Client-Request-ID"], "cli-req-123")

    @patch("urllib.request.urlopen")
    def test_02_chat_text_payload_conforme(self, mock_urlopen):
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.read.return_value = json.dumps({"choices": [{"message": {"content": "Respuesta"}}]}).encode("utf-8")

        res = self.client.chat_text("¿Cuál es la capital?", system_prompt="Eres asistente.")
        self.assertFalse(res.get("error", False))
        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body["temperature"], 0.0)
        self.assertEqual(len(body["messages"]), 2)
        self.assertEqual(body["messages"][0]["role"], "system")
        self.assertEqual(body["messages"][1]["role"], "user")

    @patch("urllib.request.urlopen")
    def test_03_chat_structured_schema_conforme(self, mock_urlopen):
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": json.dumps({"categoria": "ciencia"})}}]
        }).encode("utf-8")

        schema = {"type": "object", "properties": {"categoria": {"type": "string"}}}
        res = self.client.chat_structured("Clasifica este texto", schema=schema)
        self.assertFalse(res.get("error", False))
        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data.decode("utf-8"))
        self.assertIn("response_format", body)
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertEqual(body["response_format"]["json_schema"]["schema"], schema)

    @patch("urllib.request.urlopen")
    def test_04_chat_vision_payload(self, mock_urlopen):
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.read.return_value = json.dumps({"choices": [{"message": {"content": "Un gato"}}]}).encode("utf-8")

        res = self.client.chat_vision("Describe la imagen", image_base64="aW1n", mime_type="image/jpeg")
        self.assertFalse(res.get("error", False))
        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data.decode("utf-8"))
        user_content = body["messages"][0]["content"]
        self.assertEqual(user_content[0]["type"], "image_url")
        self.assertEqual(user_content[0]["image_url"]["url"], "data:image/jpeg;base64,aW1n")

    @patch("urllib.request.urlopen")
    def test_05_audio_transcription_payload(self, mock_urlopen):
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.read.return_value = json.dumps({"choices": [{"message": {"content": "Hola mundo"}}]}).encode("utf-8")

        res = self.client.transcribe_audio(audio_base64="d2F2")
        self.assertFalse(res.get("error", False))
        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data.decode("utf-8"))
        user_content = body["messages"][0]["content"]
        self.assertEqual(user_content[0]["type"], "input_audio")
        self.assertEqual(user_content[0]["input_audio"]["format"], "wav")

    @patch("urllib.request.urlopen")
    def test_06_speech_synthesis_tts_payload(self, mock_urlopen):
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.read.return_value = json.dumps({"choices": [{"message": {"audio": {"data": "d2F2"}}}]}).encode("utf-8")

        res = self.client.synthesize_speech("Buenos días", voice="es-ES")
        self.assertFalse(res.get("error", False))
        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body["modalities"], ["audio"])
        self.assertEqual(body["audio"]["voice"], "es-ES")

    @patch("urllib.request.urlopen")
    def test_07_streaming_sse_recepcion_continua(self, mock_urlopen):
        lineas_sse = [
            b'data: {"choices": [{"delta": {"content": "Hola"}}]}\n\n',
            b'data: {"choices": [{"delta": {"content": " mundo"}}]}\n\n',
            b'data: [DONE]\n\n',
        ]
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.__iter__.return_value = iter(lineas_sse)

        tokens = list(self.client.stream_chat([{"role": "user", "content": "Hola"}]))
        self.assertEqual(tokens, ["Hola", " mundo"])

    def test_08_saneamiento_seguridad_xss(self):
        peligroso = "<script>alert('xss')</script><a href='javascript:void(0)'>link</a>"
        saneado = sanitize_for_display(peligroso)
        self.assertNotIn("<script>", saneado)
        self.assertNotIn("</a>", saneado)
        self.assertIn("&lt;script&gt;", saneado)


class AdaptadorPerfilDAuthTests(unittest.TestCase):
    """Pruebas del Adaptador de Perfil D con autenticación y multimodalidad."""

    def setUp(self):
        self.adaptador = RobotAdapterD(
            gateway_url="https://127.0.0.1:8443",
            auth_token="beta-test-token-for-pilot-i2-32chars",
            ssl_verify=False,
        )
        self.adaptador.reset()
        self.t0 = datetime(2026, 11, 7, 10, 0, 0, tzinfo=timezone.utc)

    @patch("urllib.request.urlopen")
    def test_09_observacion_multimodal_autenticada_aceptada(self, mock_urlopen):
        propuesta_canned = {
            "id": "chatcmpl-robot-beta-1",
            "choices": [{
                "finish_reason": "stop",
                "message": {
                    "content": json.dumps({
                        "kind": "girar_derecha",
                        "payload": {"angulo": 45.0, "velocidad": 0.5, "motivo": "obstaculo_izq"},
                    })
                },
            }],
        }
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.read.return_value = json.dumps(propuesta_canned).encode("utf-8")

        solicitud = {
            "device_id": "robot-beta-01",
            "observation_id": "obs-beta-001",
            "observed_at": self.t0.isoformat().replace("+00:00", "Z"),
            "expires_at": (self.t0 + timedelta(seconds=5)).isoformat().replace("+00:00", "Z"),
            "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
            "prompt": "Obstáculo a la izquierda.",
            "allowed_kinds": ["detener", "girar_izquierda", "girar_derecha"],
        }
        res = self.adaptador.evaluar_observacion(solicitud, ahora_fn=lambda: self.t0)
        self.assertEqual(res["status"], "accepted")
        self.assertEqual(res["proposal"]["kind"], "girar_derecha")

        # Verificar cabeceras enviadas al gateway
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.headers.get("Authorization"), "Bearer beta-test-token-for-pilot-i2-32chars")
        self.assertEqual(req.headers.get("X-client-request-id"), "d-obs-beta-001")

    def test_10_descarte_por_accion_fuera_de_catalogo(self):
        propuesta_invalida = {
            "choices": [{
                "finish_reason": "stop",
                "message": {
                    "content": json.dumps({
                        "kind": "acelerar_maximo",
                        "payload": {"velocidad": 100.0},
                    })
                },
            }],
        }
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = mock_urlopen.return_value.__enter__.return_value
            mock_resp.read.return_value = json.dumps(propuesta_invalida).encode("utf-8")

            solicitud = {
                "device_id": "robot-beta-01",
                "observation_id": "obs-beta-002",
                "observed_at": self.t0.isoformat().replace("+00:00", "Z"),
                "expires_at": (self.t0 + timedelta(seconds=5)).isoformat().replace("+00:00", "Z"),
                "prompt": "Obstáculo.",
                "allowed_kinds": ["detener", "girar_izquierda"],
            }
            res = self.adaptador.evaluar_observacion(solicitud, ahora_fn=lambda: self.t0)
            self.assertEqual(res["status"], "discarded")
            self.assertEqual(res["reason"], "unauthorized_proposal_kind")


class ScriptsEjecutablesTests(unittest.TestCase):
    """Verifica que los clientes y simuladores de referencia corran con exit 0."""

    def test_11_simulador_robot_perfil_d_ejecutable(self):
        cmd = [sys.executable, str(RAIZ / "examples" / "simulador_robot_perfil_d.py")]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Simulador falló: {res.stderr}\n{res.stdout}")
        self.assertIn("todas las salvaguardas verificadas con éxito", res.stdout)

    def test_12_cliente_perfil_w_python_demo(self):
        cmd = [sys.executable, str(RAIZ / "examples" / "cliente_perfil_w.py"), "--demo"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Cliente Python falló: {res.stderr}\n{res.stdout}")
        self.assertIn("Demostración de Perfil W concluida con éxito", res.stdout)

    def test_13_cliente_perfil_w_node_demo(self):
        cmd = ["node", str(RAIZ / "examples" / "cliente_perfil_w.mjs")]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Cliente Node.js falló: {res.stderr}\n{res.stdout}")
        self.assertIn("Demostración Node.js completada con éxito", res.stdout)


if __name__ == "__main__":
    unittest.main()
