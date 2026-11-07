#!/usr/bin/env python3
"""Pruebas de la Fase I2-P — Autenticación, cuotas, colas, egreso y TLS.

Verifica la conformidad estricta con SPEC-i2-piloto-privado, ADR-009 y
servicio-general-v2:
1. Autenticación Bearer: 401 missing/invalid token, 400 missing/invalid project_id,
   403 mismatch/revoked/insufficient_scope.
2. Recarga en caliente en memoria ante revocaciones sin reinicio.
3. Limitación de tasa Token Bucket (429 rate_limit_exceeded con Retry-After).
4. Planificación justa y colas (503 overloaded y 504 queue_timeout con retryable: true).
5. Contención estricta de egreso (anti-SSRF): rechazo de file://, http://, https://, ftp://.
6. Terminador TLS stdlib en HTTPS con verificación de certificado local.
"""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
from pathlib import Path
import ssl
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

from gateway_auth import (  # noqa: E402
    FairQueueDispatcher, TokenBucket, TokenRegistry,
)
from gateway_core import ErrorV2  # noqa: E402
from gateway_http import build_server  # noqa: E402
from gateway_tls import build_tls_server  # noqa: E402

TOKEN_A = "alpha-test-token-for-pilot-i2-32chars"
TOKEN_B = "beta-test-token-for-pilot-i2-32chars"
HASH_A = hashlib.sha256(TOKEN_A.encode()).hexdigest()
HASH_B = hashlib.sha256(TOKEN_B.encode()).hexdigest()


class BackendFalsoI2(BaseHTTPRequestHandler):
    """Backend simulado de llama-server para pruebas I2."""
    count = 0

    def _json(self, status, payload):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        type(self).count += 1
        longitud = int(self.headers.get("Content-Length", 0))
        cuerpo = self.rfile.read(longitud)
        self._json(200, {
            "choices": [{"message": {"content": "respuesta backend i2"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        })

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"status": "ok"})
        elif self.path == "/v1/models":
            self._json(200, {"data": [{"id": "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M"}]})
        elif self.path == "/slots":
            self._json(200, [{"id": 0, "is_processing": False}])
        else:
            self._json(404, {"error": {"code": "not_found"}})

    def log_message(self, *a):
        pass


class TestTokenRegistry(unittest.TestCase):
    """Pruebas de verificación de identidad y recarga en caliente."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json")
        self.tokens_path = Path(self.tmp.name)
        self.data_inicial = {
            "version": 1,
            "projects": {
                "proyecto-alpha": {
                    "token_sha256": HASH_A,
                    "revoked": False,
                    "scopes": ["infer:text", "infer:vision", "infer:audio", "speech:synthesize"],
                    "rate_limit": {"requests_per_minute": 60, "burst": 5, "max_queue": 2, "queue_timeout_seconds": 10.0},
                },
                "proyecto-beta": {
                    "token_sha256": HASH_B,
                    "revoked": False,
                    "scopes": ["infer:text", "infer:vision", "profile:d"],
                    "rate_limit": {"requests_per_minute": 30, "burst": 3, "max_queue": 2, "queue_timeout_seconds": 10.0},
                },
            },
        }
        json.dump(self.data_inicial, self.tmp)
        self.tmp.flush()
        self.tmp.close()
        self.registry = TokenRegistry(self.tokens_path)

    def tearDown(self):
        if self.tokens_path.exists():
            self.tokens_path.unlink()

    def test_verificacion_exitosa(self):
        proj = self.registry.verify_request(f"Bearer {TOKEN_A}", "proyecto-alpha", "infer:text")
        self.assertIsNotNone(proj)
        self.assertIn("infer:text", proj["scopes"])

    def test_token_ausente_401(self):
        with self.assertRaises(ErrorV2) as ctx:
            self.registry.verify_request(None, "proyecto-alpha")
        self.assertEqual(ctx.exception.status, 401)
        self.assertEqual(ctx.exception.code, "missing_token")

    def test_token_invalido_formato_401(self):
        with self.assertRaises(ErrorV2) as ctx:
            self.registry.verify_request("Basic abc", "proyecto-alpha")
        self.assertEqual(ctx.exception.status, 401)
        self.assertEqual(ctx.exception.code, "invalid_token")

    def test_token_longitud_erronea_401(self):
        with self.assertRaises(ErrorV2) as ctx:
            self.registry.verify_request("Bearer corto", "proyecto-alpha")
        self.assertEqual(ctx.exception.status, 401)
        self.assertEqual(ctx.exception.code, "invalid_token")

    def test_project_id_ausente_400(self):
        with self.assertRaises(ErrorV2) as ctx:
            self.registry.verify_request(f"Bearer {TOKEN_A}", None)
        self.assertEqual(ctx.exception.status, 400)
        self.assertEqual(ctx.exception.code, "missing_project_id")

    def test_project_id_caracteres_invalidos_400(self):
        with self.assertRaises(ErrorV2) as ctx:
            self.registry.verify_request(f"Bearer {TOKEN_A}", "../proyecto-alpha")
        self.assertEqual(ctx.exception.status, 400)
        self.assertEqual(ctx.exception.code, "invalid_project_id")

    def test_project_mismatch_403(self):
        with self.assertRaises(ErrorV2) as ctx:
            self.registry.verify_request(f"Bearer {TOKEN_A}", "proyecto-beta")
        self.assertEqual(ctx.exception.status, 403)
        self.assertEqual(ctx.exception.code, "project_mismatch")

    def test_scope_insuficiente_403(self):
        with self.assertRaises(ErrorV2) as ctx:
            # proyecto-beta no tiene speech:synthesize
            self.registry.verify_request(f"Bearer {TOKEN_B}", "proyecto-beta", "speech:synthesize")
        self.assertEqual(ctx.exception.status, 403)
        self.assertEqual(ctx.exception.code, "insufficient_scope")

    def test_recarga_en_caliente_revocacion(self):
        # Inicialmente válido
        proj = self.registry.verify_request(f"Bearer {TOKEN_A}", "proyecto-alpha")
        self.assertFalse(proj["revoked"])

        # Revocar en el archivo
        self.data_inicial["projects"]["proyecto-alpha"]["revoked"] = True
        time.sleep(0.01)
        with open(self.tokens_path, "w", encoding="utf-8") as f:
            json.dump(self.data_inicial, f)

        # La siguiente llamada debe recargar en memoria y rechazar con 403 credential_revoked
        with self.assertRaises(ErrorV2) as ctx:
            self.registry.verify_request(f"Bearer {TOKEN_A}", "proyecto-alpha")
        self.assertEqual(ctx.exception.status, 403)
        self.assertEqual(ctx.exception.code, "credential_revoked")


class TestTokenBucket(unittest.TestCase):
    """Pruebas del limitador Token Bucket."""

    def test_burst_y_agotamiento(self):
        bucket = TokenBucket(requests_per_minute=60, burst=2)
        # 1er token -> permitido
        ok1, _ = bucket.acquire()
        self.assertTrue(ok1)
        # 2do token -> permitido
        ok2, _ = bucket.acquire()
        self.assertTrue(ok2)
        # 3er token consecutivo sin tiempo -> denegado
        ok3, retry_after = bucket.acquire()
        self.assertFalse(ok3)
        self.assertGreater(retry_after, 0.0)


class TestFairQueuing(unittest.TestCase):
    """Pruebas de concurrencia, colas acotadas y equidad."""

    def setUp(self):
        self.dispatcher = FairQueueDispatcher()

    def test_cola_llena_503(self):
        cfg = {"requests_per_minute": 60, "burst": 10, "max_queue": 1, "queue_timeout_seconds": 1.0}
        # Bloquear el motor
        self.dispatcher._engine_in_use = True
        # Encolar 1 petición (máximo permitido)
        t = threading.Thread(target=lambda: self.dispatcher.acquire_slot("p1", cfg))
        t.start()
        time.sleep(0.05)

        # Intentar encolar una 2da petición -> debe rebotar con 503 overloaded
        with self.assertRaises(ErrorV2) as ctx:
            self.dispatcher.acquire_slot("p1", cfg)
        self.assertEqual(ctx.exception.status, 503)
        self.assertEqual(ctx.exception.code, "overloaded")
        self.assertTrue(ctx.exception.extra.get("retryable"))

        # Limpiar
        self.dispatcher._engine_in_use = False
        self.dispatcher.release_slot("p1")
        t.join(timeout=1.0)

    def test_queue_timeout_504(self):
        cfg = {"requests_per_minute": 60, "burst": 10, "max_queue": 2, "queue_timeout_seconds": 0.1}
        self.dispatcher._engine_in_use = True
        with self.assertRaises(ErrorV2) as ctx:
            self.dispatcher.acquire_slot("p1", cfg, timeout=0.1)
        self.assertEqual(ctx.exception.status, 504)
        self.assertEqual(ctx.exception.code, "queue_timeout")
        self.assertTrue(ctx.exception.extra.get("retryable"))
        self.dispatcher._engine_in_use = False

    def test_timeout_no_libera_motor_si_otra_peticion_sigue_activa(self):
        cfg = {"requests_per_minute": 60, "burst": 10, "max_queue": 2, "queue_timeout_seconds": 0.1}
        # Simulamos que la petición A de 'p1' adquirió el motor legítimamente
        self.dispatcher._engine_in_use = True
        self.dispatcher._in_flight["p1"] = 1

        # La petición B de 'p1' intenta adquirir y expira por timeout
        with self.assertRaises(ErrorV2) as ctx:
            self.dispatcher.acquire_slot("p1", cfg, timeout=0.05)
        self.assertEqual(ctx.exception.status, 504)

        # Invariante crítica: el motor DEBE seguir en uso por la petición A activa
        self.assertTrue(self.dispatcher._engine_in_use)
        self.assertEqual(self.dispatcher._in_flight["p1"], 1)

        # Ahora la petición A concluye y libera su slot
        self.dispatcher.release_slot("p1")
        self.assertFalse(self.dispatcher._engine_in_use)
        self.assertEqual(self.dispatcher._in_flight["p1"], 0)


class TestGatewayE2EConAuth(unittest.TestCase):
    """Pruebas de integración HTTP sobre el gateway con autenticación I2 activa."""

    def setUp(self):
        self.backend = ThreadingHTTPServer(("127.0.0.1", 0), BackendFalsoI2)
        self.backend_port = self.backend.server_address[1]
        threading.Thread(target=self.backend.serve_forever, daemon=True).start()
        BackendFalsoI2.count = 0

        self.tmp = tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json")
        self.tokens_path = Path(self.tmp.name)
        data = {
            "version": 1,
            "projects": {
                "proyecto-alpha": {
                    "token_sha256": HASH_A,
                    "revoked": False,
                    "scopes": ["infer:text", "infer:vision", "infer:audio", "speech:synthesize"],
                    "rate_limit": {"requests_per_minute": 120, "burst": 10, "max_queue": 2, "queue_timeout_seconds": 5.0},
                },
                "proyecto-beta": {
                    "token_sha256": HASH_B,
                    "revoked": False,
                    "scopes": ["infer:text", "infer:vision", "profile:d"],
                    "rate_limit": {"requests_per_minute": 60, "burst": 5, "max_queue": 2, "queue_timeout_seconds": 5.0},
                },
            },
        }
        json.dump(data, self.tmp)
        self.tmp.flush()
        self.tmp.close()

        self.registry = TokenRegistry(self.tokens_path)
        self.dispatcher = FairQueueDispatcher()
        self.gateway = build_server(
            ("127.0.0.1", 0),
            backend=f"http://127.0.0.1:{self.backend_port}",
            auth_enabled=True,
            tokens_registry=self.registry,
            dispatcher=self.dispatcher,
        )
        self.port = self.gateway.server_address[1]
        threading.Thread(target=self.gateway.serve_forever, daemon=True).start()

    def tearDown(self):
        self.gateway.shutdown()
        self.gateway.server_close()
        self.backend.shutdown()
        self.backend.server_close()
        if self.tokens_path.exists():
            self.tokens_path.unlink()

    def _req(self, ruta, metodo="GET", cuerpo=None, headers=None):
        url = f"http://127.0.0.1:{self.port}{ruta}"
        req = urllib.request.Request(
            url,
            data=cuerpo,
            headers=headers or {},
            method=metodo,
        )
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                return resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), exc.headers

    def test_healthz_es_publico_sin_auth(self):
        status, body, _ = self._req("/healthz")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["status"], "ok")

    def test_capabilities_exige_auth(self):
        # Sin auth -> 401
        status, body, headers = self._req("/v1/capabilities")
        self.assertEqual(status, 401)
        self.assertIn("WWW-Authenticate", headers)
        err = json.loads(body)
        self.assertEqual(err["error"]["code"], "missing_token")

        # Con auth de proyecto-alpha -> 200
        auth_h = {
            "Authorization": f"Bearer {TOKEN_A}",
            "X-Project-ID": "proyecto-alpha",
        }
        status2, body2, headers2 = self._req("/v1/capabilities", headers=auth_h)
        self.assertEqual(status2, 200)
        self.assertEqual(headers2.get("X-Service-Contract"), "2")
        self.assertEqual(headers2.get("X-Project-Id"), "proyecto-alpha")

    def test_chat_completions_auth_exitosa(self):
        payload = {
            "model": "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M",
            "messages": [{"role": "user", "content": "hola i2"}],
        }
        cuerpo = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TOKEN_A}",
            "X-Project-ID": "proyecto-alpha",
        }
        status, body, resp_headers = self._req("/v1/chat/completions", "POST", cuerpo, headers)
        self.assertEqual(status, 200)
        self.assertEqual(resp_headers.get("X-Project-Id"), "proyecto-alpha")
        self.assertEqual(resp_headers.get("X-Service-Contract"), "2")
        self.assertIn("choices", json.loads(body))

    def test_chat_scope_insuficiente_audio_en_proyecto_beta(self):
        # proyecto-beta no tiene infer:audio
        audio_dummy = base64.b64encode(b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00").decode()
        payload = {
            "model": "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M",
            "messages": [{"role": "user", "content": [
                {"type": "input_audio", "input_audio": {"data": audio_dummy, "format": "wav"}}
            ]}],
        }
        cuerpo = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TOKEN_B}",
            "X-Project-ID": "proyecto-beta",
        }
        status, body, _ = self._req("/v1/chat/completions", "POST", cuerpo, headers)
        self.assertEqual(status, 403)
        err = json.loads(body)
        self.assertEqual(err["error"]["code"], "insufficient_scope")

    def test_anti_ssrf_rechazo_file_http_en_imagenes(self):
        for esquema in ("file:///etc/passwd", "http://evil.com/pic.png", "https://evil.com/pic.png"):
            payload = {
                "model": "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M",
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": esquema}}
                ]}],
            }
            cuerpo = json.dumps(payload).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {TOKEN_A}",
                "X-Project-ID": "proyecto-alpha",
            }
            status, body, _ = self._req("/v1/chat/completions", "POST", cuerpo, headers)
            self.assertEqual(status, 400)
            err = json.loads(body)
            self.assertEqual(err["error"]["code"], "external_url_rejected")

    def test_chat_multimodal_imagen_mas_profile_d_exige_ambos_scopes(self):
        # proyecto-alpha tiene infer:vision pero NO tiene profile:d
        png_dummy = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGP6zwAA/8cB+hkxs98AAAAASUVORK5CYII="
        schema_robot = {
            "type": "object",
            "properties": {
                "proposal": {
                    "type": "object",
                    "properties": {"kind": {"type": "string"}},
                    "required": ["kind"],
                }
            },
            "required": ["proposal"],
        }
        payload = {
            "model": "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M",
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": png_dummy}},
                {"type": "text", "text": "analizar entorno"},
            ]}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "robot_prop", "schema": schema_robot},
            },
        }
        cuerpo = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TOKEN_A}",
            "X-Project-ID": "proyecto-alpha",
        }
        status, body, _ = self._req("/v1/chat/completions", "POST", cuerpo, headers)
        self.assertEqual(status, 403)
        err = json.loads(body)
        self.assertEqual(err["error"]["code"], "insufficient_scope")
        self.assertIn("profile:d", err["error"]["message"])

    def test_anti_ssrf_video_ftp_rechazado(self):
        payload = {
            "model": "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M",
            "messages": [{"role": "user", "content": [
                {"type": "video_url", "video_url": {"url": "ftp://evil.com/video.mp4"}}
            ]}],
        }
        cuerpo = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TOKEN_A}",
            "X-Project-ID": "proyecto-alpha",
        }
        status, body, _ = self._req("/v1/chat/completions", "POST", cuerpo, headers)
        self.assertEqual(status, 400)
        err = json.loads(body)
        self.assertEqual(err["error"]["code"], "external_url_rejected")

    def test_rate_limit_exceeded_incluye_retry_after(self):
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TOKEN_B}",
            "X-Project-ID": "proyecto-beta",
        }
        payload = {
            "model": "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M",
            "messages": [{"role": "user", "content": "hola"}],
        }
        cuerpo = json.dumps(payload).encode("utf-8")
        limiter = self.dispatcher.get_limiter("proyecto-beta", {"requests_per_minute": 1, "burst": 1})
        limiter.tokens = 0.0
        status, body, resp_headers = self._req("/v1/chat/completions", "POST", cuerpo, headers)
        self.assertEqual(status, 429)
        self.assertIn("Retry-After", resp_headers)
        err = json.loads(body)
        self.assertEqual(err["error"]["code"], "rate_limit_exceeded")
        self.assertTrue(err["error"]["retryable"])

    def test_do_post_rechaza_no_autenticado_antes_de_leer_cuerpo(self):
        headers = {
            "Content-Type": "application/json",
            # Sin Authorization
            "X-Project-ID": "proyecto-alpha",
        }
        status, body, _ = self._req("/v1/chat/completions", "POST", b"{}", headers)
        self.assertEqual(status, 401)
        err = json.loads(body)
        self.assertEqual(err["error"]["code"], "missing_token")


class TestGatewayTLS(unittest.TestCase):
    """Pruebas del terminador TLS stdlib en puerto 8443."""

    def setUp(self):
        self.certs_tmp = tempfile.mkdtemp(prefix="lfm3-certs-test-")
        self.certs_dir = Path(self.certs_tmp)

        # Backend falso
        self.backend = ThreadingHTTPServer(("127.0.0.1", 0), BackendFalsoI2)
        self.backend_port = self.backend.server_address[1]
        threading.Thread(target=self.backend.serve_forever, daemon=True).start()

        # Gateway HTTP en loopback
        self.gateway = build_server(("127.0.0.1", 0), backend=f"http://127.0.0.1:{self.backend_port}")
        self.gw_port = self.gateway.server_address[1]
        threading.Thread(target=self.gateway.serve_forever, daemon=True).start()

        # Terminador TLS
        self.tls_server = build_tls_server(("127.0.0.1", 0), gateway_port=self.gw_port, certs_dir=self.certs_dir)
        self.tls_port = self.tls_server.server_address[1]
        threading.Thread(target=self.tls_server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.tls_server.shutdown()
        self.tls_server.server_close()
        self.gateway.shutdown()
        self.gateway.server_close()
        self.backend.shutdown()
        self.backend.server_close()
        import shutil
        shutil.rmtree(self.certs_tmp, ignore_errors=True)

    def test_https_get_healthz_con_cert_verificado(self):
        # Verificación estricta con contexto SSL que valida la CA local
        ctx = ssl.create_default_context(cafile=str(self.tls_server.cert_path))
        ctx.check_hostname = True

        url = f"https://localhost:{self.tls_port}/healthz"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, context=ctx, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("X-TLS-Terminator"), "lfm3-stdlib")
            body = json.loads(resp.read())
            self.assertEqual(body["status"], "ok")

    def test_tls_gateway_unreachable_devuelve_sobre_cerrado_502(self):
        # Detenemos y cerramos el gateway interno para simular caída
        self.gateway.shutdown()
        self.gateway.server_close()
        ctx = ssl.create_default_context(cafile=str(self.tls_server.cert_path))
        ctx.check_hostname = True
        url = f"https://localhost:{self.tls_port}/healthz"
        req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=5.0):
                self.fail("debió fallar con 502")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 502)
            self.assertEqual(exc.headers.get("X-TLS-Terminator"), "lfm3-stdlib")
            self.assertEqual(exc.headers.get("X-Service-Contract"), "2")
            self.assertIsNotNone(exc.headers.get("X-Request-Id"))
            err = json.loads(exc.read())
            self.assertEqual(err["error"]["code"], "backend_unreachable")
            self.assertTrue(err["error"]["retryable"])


if __name__ == "__main__":
    unittest.main()
