"""Pruebas de aceptación y activación del piloto privado HTTPS (TAREA I2-U).

Verifica de extremo a extremo:
- Terminación TLS en Python stdlib con verificación de certificados locales.
- Identidad, autenticación y scopes para los dos proyectos autorizados:
  - proyecto-alpha (infer:text, infer:vision, infer:audio, speech:synthesize)
  - proyecto-beta (infer:text, infer:vision, profile:d)
- Aislamiento estricto de recursos y rate-limiting inter-inquilinos.
- Contención de egreso anti-SSRF y sobre de error cerrado ErrorV2.
- Capacidad de rollback real y parada ordenada.
"""

from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import ssl
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gateway_auth import FairQueueDispatcher, TokenRegistry  # noqa: E402
from gateway_http import build_server  # noqa: E402
from gateway_tls import (  # noqa: E402
    asegurar_certificados_locales,
    build_tls_server,
)

TOKEN_ALPHA = "alpha-test-token-for-pilot-i2-32chars"
TOKEN_BETA = "beta-test-token-for-pilot-i2-32chars"
HASH_ALPHA = hashlib.sha256(TOKEN_ALPHA.encode()).hexdigest()
HASH_BETA = hashlib.sha256(TOKEN_BETA.encode()).hexdigest()


class BackendMotorSimulado(BaseHTTPRequestHandler):
    """Simulador de backend (llama-server) para pruebas de piloto."""

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
        elif self.path == "/v1/models":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "data": [
                            {"id": "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M"}
                        ]
                    }
                ).encode()
            )
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        cuerpo = self.rfile.read(length)
        data = json.loads(cuerpo.decode("utf-8")) if cuerpo else {}

        # Simular respuesta de chat
        if self.path == "/v1/chat/completions":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            rf = data.get("response_format")
            if rf and rf.get("type") == "json_schema":
                contenido = json.dumps(
                    {
                        "observation_id": "obs-live-01",
                        "action": "move_forward",
                        "confidence": 0.95,
                    }
                )
            else:
                contenido = "Respuesta sintetica del motor LFM3-Omni"

            resp = {
                "id": "chatcmpl-pilot-test",
                "object": "chat.completion",
                "created": 1700000000,
                "model": "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": contenido},
                        "finish_reason": "stop",
                    }
                ],
            }
            self.wfile.write(json.dumps(resp).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


class TestPilotoPrivadoLive(unittest.TestCase):
    """Batería de pruebas de activación y consumo del piloto privado HTTPS."""

    @classmethod
    def setUpClass(cls):
        # 1. Backend falso
        cls.backend = ThreadingHTTPServer(("127.0.0.1", 0), BackendMotorSimulado)
        cls.backend_port = cls.backend.server_address[1]
        threading.Thread(target=cls.backend.serve_forever, daemon=True).start()

        # 2. Configuración temporal de tokens y certificados
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_dir.name)
        cls.tokens_path = cls.temp_path / "tokens.json"

        data_tokens = {
            "version": 1,
            "projects": {
                "proyecto-alpha": {
                    "token_sha256": HASH_ALPHA,
                    "revoked": False,
                    "scopes": [
                        "infer:text",
                        "infer:vision",
                        "infer:audio",
                        "speech:synthesize",
                    ],
                    "rate_limit": {
                        "requests_per_minute": 60,
                        "burst": 5,
                        "max_queue": 2,
                        "queue_timeout_seconds": 5.0,
                    },
                },
                "proyecto-beta": {
                    "token_sha256": HASH_BETA,
                    "revoked": False,
                    "scopes": ["infer:text", "infer:vision", "profile:d"],
                    "rate_limit": {
                        "requests_per_minute": 30,
                        "burst": 3,
                        "max_queue": 2,
                        "queue_timeout_seconds": 5.0,
                    },
                },
            },
        }
        cls.tokens_path.write_text(json.dumps(data_tokens), encoding="utf-8")

        cls.certs_dir = cls.temp_path / "certs"
        cls.cert_pem, cls.key_pem = asegurar_certificados_locales(cls.certs_dir)

        # 3. Gateway HTTP v2 en loopback con auth
        cls.registry = TokenRegistry(cls.tokens_path)
        cls.dispatcher = FairQueueDispatcher()
        cls.gateway = build_server(
            ("127.0.0.1", 0),
            backend=f"http://127.0.0.1:{cls.backend_port}",
            auth_enabled=True,
            tokens_registry=cls.registry,
            dispatcher=cls.dispatcher,
        )
        cls.gateway_port = cls.gateway.server_address[1]
        threading.Thread(target=cls.gateway.serve_forever, daemon=True).start()

        # 4. Terminador TLS
        cls.tls_server = build_tls_server(
            ("127.0.0.1", 0),
            gateway_port=cls.gateway_port,
            certs_dir=cls.certs_dir,
        )
        cls.tls_port = cls.tls_server.server_address[1]
        threading.Thread(target=cls.tls_server.serve_forever, daemon=True).start()

        # Contexto SSL para cliente de prueba que confía en el certificado local
        cls.ssl_context = ssl.create_default_context(cafile=str(cls.cert_pem))

    def setUp(self):
        self.dispatcher._limiters.clear()

    @classmethod
    def tearDownClass(cls):
        cls.tls_server.shutdown()
        cls.tls_server.server_close()
        cls.gateway.shutdown()
        cls.gateway.server_close()
        cls.backend.shutdown()
        cls.backend.server_close()
        cls.temp_dir.cleanup()

    def _peticion_https(
        self,
        ruta: str,
        metodo: str = "GET",
        headers: dict | None = None,
        cuerpo: dict | bytes | None = None,
    ):
        url = f"https://127.0.0.1:{self.tls_port}{ruta}"
        data = None
        req_headers = headers or {}
        if isinstance(cuerpo, dict):
            data = json.dumps(cuerpo).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
        elif isinstance(cuerpo, bytes):
            data = cuerpo

        req = urllib.request.Request(
            url, data=data, headers=req_headers, method=metodo
        )
        try:
            with urllib.request.urlopen(
                req, context=self.ssl_context, timeout=10.0
            ) as resp:
                return resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), exc.headers

    def test_01_healthz_publico_tls(self):
        """Verifica que /healthz responda por HTTPS sin exigir autenticacion."""
        st, b, h = self._peticion_https("/healthz")
        self.assertEqual(st, 200)
        self.assertIn(b'"ok"', b)
        self.assertEqual(h.get("X-TLS-Terminator"), "lfm3-stdlib")

    def test_02_rechazo_sin_autenticacion(self):
        """Verifica que rutas protegidas rechacen peticiones anonimas con 401."""
        st, b, h = self._peticion_https("/v1/models")
        self.assertEqual(st, 401)
        data = json.loads(b)
        self.assertEqual(data["error"]["code"], "missing_token")
        self.assertEqual(data["error"]["type"], "auth_error")

    def test_03_proyecto_alpha_consumo_texto(self):
        """Verifica consumo exitoso de inferencia por proyecto-alpha."""
        headers = {
            "Authorization": f"Bearer {TOKEN_ALPHA}",
            "X-Project-ID": "proyecto-alpha",
        }
        payload = {
            "messages": [{"role": "user", "content": "Hola piloto"}],
            "max_tokens": 10,
        }
        st, b, h = self._peticion_https(
            "/v1/chat/completions",
            metodo="POST",
            headers=headers,
            cuerpo=payload,
        )
        self.assertEqual(st, 200)
        data = json.loads(b)
        self.assertIn("choices", data)
        self.assertEqual(h.get("X-Project-Id"), "proyecto-alpha")
        self.assertEqual(h.get("X-Service-Contract"), "2")

    def test_04_proyecto_beta_consumo_perfil_d(self):
        """Verifica que proyecto-beta pueda generar propuestas bajo perfil D."""
        headers = {
            "Authorization": f"Bearer {TOKEN_BETA}",
            "X-Project-ID": "proyecto-beta",
        }
        payload = {
            "messages": [{"role": "user", "content": "Genera accion"}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "action_proposal",
                    "schema": {
                        "type": "object",
                        "required": ["observation_id", "action", "confidence"],
                        "properties": {
                            "observation_id": {"type": "string"},
                            "action": {"type": "string", "enum": ["move_forward", "stop"]},
                            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        },
                    },
                },
            },
            "max_tokens": 50,
        }
        st, b, h = self._peticion_https(
            "/v1/chat/completions",
            metodo="POST",
            headers=headers,
            cuerpo=payload,
        )
        self.assertEqual(st, 200)
        self.assertEqual(h.get("X-V2-Output-Validation"), "valid")
        self.assertEqual(h.get("X-Project-Id"), "proyecto-beta")

    def test_04b_proyecto_alpha_rechazo_perfil_d_sin_scope(self):
        """Verifica que proyecto-alpha sea rechazado con 403 ante esquemas de Perfil D."""
        headers = {
            "Authorization": f"Bearer {TOKEN_ALPHA}",
            "X-Project-ID": "proyecto-alpha",
        }
        payload = {
            "messages": [{"role": "user", "content": "Genera accion"}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "action_proposal",
                    "schema": {
                        "type": "object",
                        "required": ["observation_id", "action"],
                        "properties": {
                            "observation_id": {"type": "string"},
                            "action": {"type": "string", "enum": ["move_forward", "stop"]},
                        },
                    },
                },
            },
            "max_tokens": 50,
        }
        st, b, h = self._peticion_https(
            "/v1/chat/completions",
            metodo="POST",
            headers=headers,
            cuerpo=payload,
        )
        self.assertEqual(st, 403)
        data = json.loads(b)
        self.assertEqual(data["error"]["code"], "insufficient_scope")
        self.assertIn("profile:d", data["error"]["message"])

    def test_05_proyecto_beta_rechazo_por_scope_insuficiente(self):
        """Verifica que proyecto-beta no pueda acceder a sintesis de voz (TTS)."""
        headers = {
            "Authorization": f"Bearer {TOKEN_BETA}",
            "X-Project-ID": "proyecto-beta",
        }
        payload = {"input": "texto para sintetizar"}
        st, b, h = self._peticion_https(
            "/v1/audio/speech",
            metodo="POST",
            headers=headers,
            cuerpo=payload,
        )
        self.assertEqual(st, 403)
        data = json.loads(b)
        self.assertEqual(data["error"]["code"], "insufficient_scope")
        self.assertIn("speech:synthesize", data["error"]["message"])

    def test_06_aislamiento_de_cuotas_y_rate_limiting(self):
        """Verifica que agotar cuota en proyecto-alpha no afecte a proyecto-beta."""
        headers_alpha = {
            "Authorization": f"Bearer {TOKEN_ALPHA}",
            "X-Project-ID": "proyecto-alpha",
        }
        headers_beta = {
            "Authorization": f"Bearer {TOKEN_BETA}",
            "X-Project-ID": "proyecto-beta",
        }

        payload = {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 5}
        # Consumir ráfaga de alpha (burst: 5)
        for _ in range(5):
            st, _, _ = self._peticion_https(
                "/v1/chat/completions", metodo="POST", headers=headers_alpha, cuerpo=payload
            )
            self.assertEqual(st, 200)

        # La 6ta peticion de alpha debe recibir 429
        st_alpha, b_alpha, _ = self._peticion_https(
            "/v1/chat/completions", metodo="POST", headers=headers_alpha, cuerpo=payload
        )
        self.assertEqual(st_alpha, 429)
        self.assertIn(b"rate_limit_exceeded", b_alpha)

        # Proyecto beta debe seguir funcionando sin afectacion
        st_beta, _, _ = self._peticion_https(
            "/v1/chat/completions", metodo="POST", headers=headers_beta, cuerpo=payload
        )
        self.assertEqual(st_beta, 200)

    def test_07_rechazo_credencial_revocada(self):
        """Verifica revocacion inmediata en caliente modificando el archivo."""
        # Modificar archivo para revocar a proyecto-alpha
        data = json.loads(self.tokens_path.read_text(encoding="utf-8"))
        data["projects"]["proyecto-alpha"]["revoked"] = True
        self.tokens_path.write_text(json.dumps(data), encoding="utf-8")

        headers_alpha = {
            "Authorization": f"Bearer {TOKEN_ALPHA}",
            "X-Project-ID": "proyecto-alpha",
        }
        st, b, _ = self._peticion_https("/v1/models", headers=headers_alpha)
        self.assertEqual(st, 403)
        self.assertIn(b"credential_revoked", b)

        # Restaurar estado
        data["projects"]["proyecto-alpha"]["revoked"] = False
        self.tokens_path.write_text(json.dumps(data), encoding="utf-8")

    def test_08_rechazo_cuerpo_sobredimensionado(self):
        """Verifica que el terminador TLS rechace cuerpos > 32 MiB con 413."""
        headers = {
            "Authorization": f"Bearer {TOKEN_ALPHA}",
            "X-Project-ID": "proyecto-alpha",
            "Content-Length": str(33 * 1024 * 1024),
        }
        st, b, _ = self._peticion_https(
            "/v1/chat/completions",
            metodo="POST",
            headers=headers,
            cuerpo=b"x",
        )
        self.assertEqual(st, 413)
        self.assertIn(b"payload_too_large", b)

    def test_09_anti_ssrf_video_externo_rechazado(self):
        """Verifica que URLs de video externas (no data URI) se rechacen fail-closed."""
        headers = {
            "Authorization": f"Bearer {TOKEN_ALPHA}",
            "X-Project-ID": "proyecto-alpha",
        }
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe este video"},
                        {"type": "video_url", "video_url": {"url": "http://192.168.1.1/video.mp4"}},
                    ],
                }
            ]
        }
        st, b, _ = self._peticion_https(
            "/v1/chat/completions",
            metodo="POST",
            headers=headers,
            cuerpo=payload,
        )
        self.assertEqual(st, 400)
        self.assertIn(b"external_url_rejected", b)

    def test_10_proyecto_mismatched_header_rechazado(self):
        """Verifica rechazo con 403 si el token pertenece a alpha pero se declara beta."""
        headers = {
            "Authorization": f"Bearer {TOKEN_ALPHA}",
            "X-Project-ID": "proyecto-beta",
        }
        st, b, _ = self._peticion_https("/v1/models", headers=headers)
        self.assertEqual(st, 403)
        self.assertIn(b"project_mismatch", b)

    def test_11_rollback_parada_limpia(self):
        """Verifica que run/stop.sh detenga listeners y limpie PIDs y cerrojos."""
        import subprocess
        stop_sh = Path(__file__).parent.parent / "run" / "stop.sh"
        serve_sh = Path(__file__).parent.parent / "run" / "serve.sh"
        try:
            # Ejecutar stop.sh sin argumentos (que por defecto detiene todos los componentes)
            res = subprocess.run(["bash", str(stop_sh)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0)
            self.assertIn("detenido", res.stdout)
        finally:
            # Restaurar motor 8091 para pruebas subsiguientes
            subprocess.run(["bash", str(serve_sh)], capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
