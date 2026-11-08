#!/usr/bin/env python3
"""Pruebas unitarias e integradas para la Fase I5 (Perfil J: Trabajos Largos).

Verifica exhaustivamente:
1. Canonicalización JSON RFC 8785 y hashing determinista.
2. Persistencia atómica y durabilidad en disco.
3. Garantía de idempotencia:
   - Mismo cuerpo + misma clave -> 202 con mismo job_id.
   - Distinto cuerpo + misma clave -> 409 Conflict (idempotency_conflict).
4. Aislamiento multi-inquilino (visibilidad nula para proyectos ajenos -> 404).
5. Límites de cola por proyecto (429 si se satura).
6. Cancelación segura por DELETE (en cola y en ejecución).
7. Recuperación determinista tras reinicio (running pasa a failed con outcome unknown).
8. Integración HTTP contra servidor gateway en loopback.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid

import sys
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "examples"))

from gateway_auth import FairQueueDispatcher, TokenRegistry
from gateway_http import build_server
from jobs_manager import JobsManager, canonical_json_rfc8785
from tests.engine_probe import probe_engine  # noqa: E402


TOKEN_A = "alpha-test-token-for-pilot-i5-32chars"
TOKEN_B = "beta-test-token-for-pilot-i5-32chars"

# fix-tests-hermeticos P2 (intento 2): el flujo HTTP completo de /jobs
# necesita el motor vivo porque sin él el job muere al instante y la
# cancelación llega como already_terminal. La ausencia verificada
# (conexión rehusada) salta el test con motivo; un error de sonda hace
# fallar la guarda con su motivo.
ENGINE_UP, PROBE_ERROR = probe_engine()


class CanonicalJsonRFC8785Tests(unittest.TestCase):
    """Pruebas de la canonicalización determinista según RFC 8785."""

    def test_01_orden_lexicografico_de_claves(self):
        obj1 = {"z": 1, "a": 2, "m": {"b": 3, "a": 4}}
        obj2 = {"a": 2, "m": {"a": 4, "b": 3}, "z": 1}
        canon1 = canonical_json_rfc8785(obj1)
        canon2 = canonical_json_rfc8785(obj2)
        self.assertEqual(canon1, canon2)
        self.assertEqual(canon1, b'{"a":2,"m":{"a":4,"b":3},"z":1}')

    def test_02_rechazo_valores_no_finitos(self):
        with self.assertRaises(ValueError):
            canonical_json_rfc8785({"invalido": float("nan")})
        with self.assertRaises(ValueError):
            canonical_json_rfc8785({"invalido": float("inf")})


class JobsManagerDirectTests(unittest.TestCase):
    """Pruebas unitarias directas del motor JobsManager."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_test_jobs_"))
        self.manager = JobsManager(jobs_dir=self.temp_dir)

    def tearDown(self):
        self.manager.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_03_crear_job_e_idempotencia_coincidente(self):
        payload = {"messages": [{"role": "user", "content": "Analizar"}], "max_tokens": 128}
        status, res = self.manager.create_job(
            project_id="proyecto-alpha",
            operation="infer_text",
            payload=payload,
            idempotency_key="key-test-01",
        )
        self.assertEqual(status, 202)
        job_id = res["job_id"]
        self.assertEqual(res["state"], "queued")

        # Reintento idéntico con misma clave y mismo payload
        status_dup, res_dup = self.manager.create_job(
            project_id="proyecto-alpha",
            operation="infer_text",
            payload=payload,
            idempotency_key="key-test-01",
        )
        self.assertEqual(status_dup, 202)
        self.assertEqual(res_dup["job_id"], job_id)

    def test_04_conflicto_idempotencia_payload_distinto(self):
        payload1 = {"messages": [{"role": "user", "content": "Analizar 1"}]}
        payload2 = {"messages": [{"role": "user", "content": "Analizar 2"}]}

        status1, _ = self.manager.create_job(
            project_id="proyecto-alpha",
            operation="infer_text",
            payload=payload1,
            idempotency_key="key-conflicto-01",
        )
        self.assertEqual(status1, 202)

        # Misma clave con cuerpo distinto -> 409 Conflict
        status2, res2 = self.manager.create_job(
            project_id="proyecto-alpha",
            operation="infer_text",
            payload=payload2,
            idempotency_key="key-conflicto-01",
        )
        self.assertEqual(status2, 409)
        self.assertEqual(res2["error"]["code"], "idempotency_conflict")

    def test_05_aislamiento_multi_inquilino(self):
        payload = {"prompt": "Texto privado"}
        status, res = self.manager.create_job(
            project_id="proyecto-alpha",
            operation="infer_text",
            payload=payload,
            idempotency_key="key-alpha-privada",
        )
        job_id = res["job_id"]

        # Proyecto Beta intenta consultar el job de Proyecto Alpha -> 404
        status_beta, res_beta = self.manager.get_job("proyecto-beta", job_id)
        self.assertEqual(status_beta, 404)
        self.assertEqual(res_beta["error"]["code"], "not_found")

        # Proyecto Beta intenta cancelar el job de Proyecto Alpha -> 404
        status_del, res_del = self.manager.cancel_job("proyecto-beta", job_id)
        self.assertEqual(status_del, 404)

        # Proyecto Alpha sí puede consultarlo
        status_alpha, res_alpha = self.manager.get_job("proyecto-alpha", job_id)
        self.assertEqual(status_alpha, 200)
        self.assertEqual(res_alpha["job_id"], job_id)

    def test_06_limite_de_cola_por_proyecto(self):
        payload = {"prompt": "Trabajo 1"}
        status1, _ = self.manager.create_job(
            project_id="proyecto-alpha",
            operation="infer_text",
            payload=payload,
            idempotency_key="key-q-1",
        )
        self.assertEqual(status1, 202)

        # Segundo trabajo antes de que se libere el primero -> 429
        status2, res2 = self.manager.create_job(
            project_id="proyecto-alpha",
            operation="infer_text",
            payload={"prompt": "Trabajo 2"},
            idempotency_key="key-q-2",
        )
        self.assertEqual(status2, 429)
        self.assertEqual(res2["error"]["code"], "queue_limit_per_project_exceeded")

    def test_07_cancelacion_de_job_en_cola(self):
        payload = {"prompt": "Trabajo a cancelar"}
        status, res = self.manager.create_job(
            project_id="proyecto-alpha",
            operation="infer_text",
            payload=payload,
            idempotency_key="key-cancel-01",
        )
        job_id = res["job_id"]

        status_del, res_del = self.manager.cancel_job("proyecto-alpha", job_id)
        self.assertEqual(status_del, 200)
        self.assertEqual(res_del["cancellation_status"], "accepted")
        self.assertEqual(res_del["target_state"], "cancelled")

        # Segunda cancelación sobre estado terminal
        status_del2, res_del2 = self.manager.cancel_job("proyecto-alpha", job_id)
        self.assertEqual(status_del2, 200)
        self.assertEqual(res_del2["cancellation_status"], "already_terminal")

    def test_08_recuperacion_reinicio_running_pasa_a_failed(self):
        # Simular un trabajo que quedó en 'running' cuando el proceso colapsó
        proj_dir = self.temp_dir / "data" / "proyecto-alpha"
        proj_dir.mkdir(parents=True, exist_ok=True)
        job_crashed = {
            "job_id": "job-crashed-123",
            "contract_version": "2",
            "project_id": "proyecto-alpha",
            "operation": "infer_text",
            "state": "running",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        }
        (proj_dir / "job-crashed-123.json").write_text(json.dumps(job_crashed), encoding="utf-8")

        # Arrancar un nuevo JobsManager sobre el mismo directorio
        nuevo_manager = JobsManager(jobs_dir=self.temp_dir)
        try:
            status, res = nuevo_manager.get_job("proyecto-alpha", "job-crashed-123")
            self.assertEqual(status, 200)
            self.assertEqual(res["state"], "failed")
            self.assertEqual(res["error"]["code"], "server_interrupted")
        finally:
            nuevo_manager.stop()


class JobsGatewayIntegrationTests(unittest.TestCase):
    """Pruebas integradas de endpoints /jobs sobre servidor HTTP."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_gw_jobs_"))
        cls.tokens_path = cls.temp_dir / "tokens.json"
        config_tokens = {
            "version": 1,
            "projects": {
                "proyecto-alpha": {
                    "token_sha256": hashlib.sha256(TOKEN_A.encode("utf-8")).hexdigest(),
                    "revoked": False,
                    "scopes": ["jobs:create", "jobs:read", "jobs:cancel", "infer:text"],
                    "rate_limit": {"requests_per_minute": 100, "burst": 10, "max_concurrent": 2, "max_queue": 4, "queue_timeout_seconds": 5.0},
                },
                "proyecto-beta": {
                    "token_sha256": hashlib.sha256(TOKEN_B.encode("utf-8")).hexdigest(),
                    "revoked": False,
                    "scopes": ["infer:text", "jobs:read"],  # Sin jobs:create
                    "rate_limit": {"requests_per_minute": 100, "burst": 10, "max_concurrent": 2, "max_queue": 4, "queue_timeout_seconds": 5.0},
                },
            },
        }
        cls.tokens_path.write_text(json.dumps(config_tokens), encoding="utf-8")

        cls.registry = TokenRegistry(cls.tokens_path)
        cls.dispatcher = FairQueueDispatcher()
        cls.server = build_server(
            ("127.0.0.1", 0),
            backend="http://127.0.0.1:8091",
            auth_enabled=True,
            tokens_registry=cls.registry,
            dispatcher=cls.dispatcher,
        )
        # Apuntar jobs_manager a directorio temporal
        cls.server.jobs_manager.stop()
        cls.server.jobs_manager = JobsManager(jobs_dir=cls.temp_dir)

        cls.puerto = cls.server.server_address[1]
        cls.hilo = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.hilo.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.jobs_manager.stop()
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_09_post_jobs_http_flujo_completo(self):
        if PROBE_ERROR:
            self.fail(f"sonda de motor: {PROBE_ERROR}")
        if not ENGINE_UP:
            self.skipTest(
                "requiere motor vivo en 127.0.0.1:8091 (backend del "
                "gateway); sonda: conexión rehusada, nada escucha. Sin "
                "motor la cancelación del job llega already_terminal")
        url = f"http://127.0.0.1:{self.puerto}/jobs"
        payload = {
            "operation": "infer_text",
            "payload": {"messages": [{"role": "user", "content": "Hola jobs"}]},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {TOKEN_A}",
                "X-Project-ID": "proyecto-alpha",
                "Idempotency-Key": "idemp-http-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 202)
            data = json.loads(resp.read().decode("utf-8"))
            job_id = data["job_id"]
            self.assertEqual(data["state"], "queued")

        # GET /jobs/{id}
        url_get = f"http://127.0.0.1:{self.puerto}/jobs/{job_id}"
        req_get = urllib.request.Request(
            url_get,
            headers={
                "Authorization": f"Bearer {TOKEN_A}",
                "X-Project-ID": "proyecto-alpha",
            },
            method="GET",
        )
        with urllib.request.urlopen(req_get, timeout=5.0) as resp_get:
            self.assertEqual(resp_get.status, 200)
            data_get = json.loads(resp_get.read().decode("utf-8"))
            self.assertEqual(data_get["job_id"], job_id)

        # DELETE /jobs/{id}
        req_del = urllib.request.Request(
            url_get,
            headers={
                "Authorization": f"Bearer {TOKEN_A}",
                "X-Project-ID": "proyecto-alpha",
            },
            method="DELETE",
        )
        with urllib.request.urlopen(req_del, timeout=5.0) as resp_del:
            self.assertEqual(resp_del.status, 200)
            data_del = json.loads(resp_del.read().decode("utf-8"))
            # Con la frontera corregida el job puede haber alcanzado un
            # estado terminal (p. ej. failed por backend caído) antes del
            # DELETE; already_terminal también es respuesta de contrato.
            self.assertIn(data_del["cancellation_status"],
                          ("accepted", "pending", "already_terminal"))

    def test_10_rechazo_por_scope_insuficiente(self):
        # Proyecto Beta no tiene scope jobs:create -> 403
        url = f"http://127.0.0.1:{self.puerto}/jobs"
        payload = {"operation": "infer_text", "payload": {}}
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {TOKEN_B}",
                "X-Project-ID": "proyecto-beta",
                "Idempotency-Key": "key-beta-sin-scope",
            },
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5.0)
        self.assertEqual(ctx.exception.code, 403)

    def test_11_cliente_jobs_script(self):
        import subprocess
        cmd = [
            sys.executable,
            str(RAIZ / "examples" / "cliente_jobs_i5.py"),
            "--url", f"http://127.0.0.1:{self.puerto}",
            "--token", TOKEN_A,
            "--beta-token", TOKEN_B,
            "--project", "proyecto-alpha",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Error: {res.stderr}\n{res.stdout}")
        self.assertIn("Demostración de Perfil J completada con éxito", res.stdout)


if __name__ == "__main__":
    unittest.main()
