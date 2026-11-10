#!/usr/bin/env python3
"""Pruebas de frontera del Perfil J — expediente fix-i5-jobs-frontera.

Cubre las propiedades exigidas por el mandato (RED primero, `04` §3) y
las regresiones cerradas tras la ronda adversarial: scope de modalidad
y dialecto del payload en POST /jobs; claves duplicadas rechazadas;
salida truncada o fuera de esquema termina en fallo explícito;
durabilidad de la admisión (sin 202 sin escritura; sin registro, sin
ejecución); reclamo atómico entre instancias y admisión compartida;
retención (purga verificable, permisos 0600/0700, expires desde el
terminal); RFC 8785 (números ES6, claves UTF-16). Los tests del
expediente fix-i5-despacho viven en tests/test_jobs_despacho_i5.py
(contención de tamaño §3.4; referencia recíproca entre partes).

Fixtures numéricos: generados contra Node.js v26.7.0 (V8), consistente
con RFC 8785 §3.2.2.3 (forma ES6), verificados el 2026-11-07. El orden
de claves sigue el ejemplo de ordenación de propiedades del mismo RFC.
Los tests usan siempre data_dir temporal y un backend falso en puerto
efímero; nunca run/jobs ni 8091.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock
import urllib.error
import urllib.request
import uuid

import sys
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from gateway_auth import FairQueueDispatcher, TokenRegistry
from gateway_http import build_server
from jobs_manager import JobsManager, canonical_json_rfc8785


TOKEN_ALPHA = "alpha-boundary-token-for-i5-32chars"
TOKEN_GAMMA = "gamma-boundary-token-for-i5-32chars"
TOKEN_DELTA = "delta-boundary-token-for-i5-32chars"

RESPUESTA_VALIDA = {
    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]
}
ESTADOS_TERMINALES = {"succeeded", "failed", "cancelled"}


# ------------------------------------------------------------ backend falso
class _ManejadorFalso(BaseHTTPRequestHandler):
    def do_POST(self):
        longitud = int(self.headers.get("Content-Length", "0"))
        crudo = self.rfile.read(longitud)
        server = self.server
        with server.cerrojo:
            server.registro.append(json.loads(crudo.decode("utf-8")))
        time.sleep(server.retardo_s)
        cuerpo = json.dumps(server.respuesta).encode("utf-8")
        self.send_response(server.estado)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, formato, *args):
        pass


class BackendFalso(ThreadingHTTPServer):
    """Backend /v1/chat/completions falso en puerto efímero."""

    daemon_threads = True

    def __init__(self, respuesta=None, retardo_s=0.0, estado=200):
        self.respuesta = respuesta if respuesta is not None else RESPUESTA_VALIDA
        self.retardo_s = retardo_s
        self.estado = estado
        self.registro = []
        self.cerrojo = threading.Lock()
        super().__init__(("127.0.0.1", 0), _ManejadorFalso)
        self.hilo = threading.Thread(
            target=self.serve_forever, daemon=True)
        self.hilo.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"

    def cuenta_por_marcador(self, marcador: str) -> int:
        with self.cerrojo:
            return sum(
                1
                for cuerpo in self.registro
                if marcador
                in json.dumps(cuerpo.get("messages", []))
            )


def _esperar_terminal(manager, project_id, job_id, plazo=20.0) -> dict:
    limite = time.monotonic() + plazo
    while True:
        status, res = manager.get_job(project_id, job_id)
        if status == 200 and res.get("state") in ESTADOS_TERMINALES:
            return res
        if time.monotonic() >= limite:
            raise AssertionError(
                f"job {job_id} no terminal: {status} {res}")
        time.sleep(0.05)


def _escribir_job_en_disco(
    raiz: Path, project_id: str, job_id: str, payload: dict,
    clave: str | None = None, ttl: int = 3600,
) -> None:
    """Escribe un job 'queued' a mano; con clave, también su registro."""
    ahora = datetime.now(timezone.utc)
    job = {
        "job_id": job_id, "contract_version": "2",
        "project_id": project_id, "operation": "infer_text",
        "payload": payload, "state": "queued",
        "created_at": ahora.isoformat(), "started_at": None,
        "completed_at": None,
        "expires_at": (ahora + timedelta(seconds=ttl)).isoformat(),
        "result": None, "error": None,
        "model_revision": "LiquidAI/LFM3-Omni-2B-GGUF",
    }
    if clave is not None:
        job["idempotency_key"] = clave
        job["ttl_seconds"] = ttl
    dir_data = raiz / "data" / project_id
    dir_data.mkdir(parents=True, exist_ok=True)
    (dir_data / f"{job_id}.json").write_text(
        json.dumps(job), encoding="utf-8")
    if clave is not None:
        hash_payload = hashlib.sha256(canonical_json_rfc8785(
            {"operation": "infer_text", "payload": payload})).hexdigest()
        dir_idem = raiz / "idempotency" / project_id
        dir_idem.mkdir(parents=True, exist_ok=True)
        hash_clave = hashlib.sha256(clave.encode("utf-8")).hexdigest()
        registro = {
            "key": clave,
            "job_id": job_id,
            "payload_hash": hash_payload,
            "expires_at": (ahora + timedelta(hours=24)).isoformat(),
        }
        (dir_idem / f"{hash_clave}.json").write_text(
            json.dumps(registro), encoding="utf-8")


# ------------------------------------------------- RFC 8785: números ES6
class CanonicalRFC8785NumerosTests(unittest.TestCase):
    """Forma ES6 de números y orden UTF-16 de claves (RFC 8785)."""

    FIXTURES = [
        (0.0, "0"),
        (-0.0, "0"),
        (1.0, "1"),
        (4.50, "4.5"),
        (2e-3, "0.002"),
        (1e-6, "0.000001"),
        (1e-7, "1e-7"),
        (1e16, "10000000000000000"),
        (1e20, "100000000000000000000"),
        (1e21, "1e+21"),
        (1e30, "1e+30"),
        (1e-27, "1e-27"),
        (5e-324, "5e-324"),
        (1.5e-9, "1.5e-9"),
        (3.141592653589793, "3.141592653589793"),
        (1.7976931348623157e308, "1.7976931348623157e+308"),
        (2.2250738585072014e-308, "2.2250738585072014e-308"),
        (-1.7976931348623157e308, "-1.7976931348623157e+308"),
        (float("123456789012345678901"), "123456789012345680000"),
        (333333333.33333329, "333333333.3333333"),
    ]

    def test_01_forma_es6_de_numeros(self):
        for valor, esperado in self.FIXTURES:
            con_solo = canonical_json_rfc8785({"n": valor})
            self.assertEqual(
                con_solo, f'{{"n":{esperado}}}'.encode("utf-8"),
                f"forma canónica de {valor!r}",
            )

    def test_02_enteros_fuera_del_rango_doble(self):
        # RFC 8785 asume dobles IEEE 754: fuera de ±(2^53-1) no hay
        # serialización canónica definida; debe rechazarse.
        with self.assertRaises(ValueError):
            canonical_json_rfc8785({"n": 2**53 + 1})
        self.assertEqual(
            canonical_json_rfc8785({"n": 2**53 - 1}),
            b'{"n":9007199254740991}',
        )

    def test_03_orden_de_claves_por_utf16(self):
        objeto = {
            "\u20ac": "Euro Sign",
            "\r": "Carriage Return",
            "\ufb33": "Hebrew Letter Dalet With Dagesh",
            "\u00fc": "Latin Small Letter U With Diaeresis",
            "\u000a": "Line Feed",
            "\U0001f600": "Emoji: Grinning Face",
            "\u0061": "Latin Small Letter A",
        }
        esperado = (
            '{"\\n":"Line Feed","\\r":"Carriage Return",'
            '"a":"Latin Small Letter A",'
            '"ü":"Latin Small Letter U With Diaeresis",'
            '"€":"Euro Sign",'
            '"\U0001f600":"Emoji: Grinning Face",'
            '"\ufb33":"Hebrew Letter Dalet With Dagesh"}'
        )
        self.assertEqual(
            canonical_json_rfc8785(objeto), esperado.encode("utf-8"))

    def test_04_escapes_minimos_de_cadena(self):
        casos = [
            ('a"b\\c', b'"a\\"b\\\\c"'),
            ("\t\n\r\b\f", b'"\\t\\n\\r\\b\\f"'),
            ("\u0001", b'"\\u0001"'),
            ("\u007f", b'"\x7f"'),  # DEL sale crudo en forma ES6
            ("ñ", '"ñ"'.encode("utf-8")),
        ]
        for valor, esperado in casos:
            self.assertEqual(
                canonical_json_rfc8785(valor), esperado,
                f"escape de {valor!r}",
            )

    def test_05_no_finitos_rechazados(self):
        for malo in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                canonical_json_rfc8785({"n": malo})


# -------------------------------------------- frontera HTTP de POST /jobs
class FronteraJobsHTTPTests(unittest.TestCase):
    """POST /jobs exige scope de modalidad y dialecto v2 del payload."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_bnd_http_"))
        cls.tokens_path = cls.temp_dir / "tokens.json"
        rl = {"requests_per_minute": 600, "burst": 50, "max_queue": 10,
              "queue_timeout_seconds": 5.0}
        config = {
            "version": 1,
            "projects": {
                "proyecto-alpha": {
                    "token_sha256": hashlib.sha256(
                        TOKEN_ALPHA.encode()).hexdigest(),
                    "revoked": False,
                    "scopes": ["jobs:create", "jobs:read", "jobs:cancel",
                               "infer:text", "infer:vision", "infer:audio"],
                    "rate_limit": rl},
                "proyecto-gamma": {  # jobs:* pero SIN infer:*
                    "token_sha256": hashlib.sha256(
                        TOKEN_GAMMA.encode()).hexdigest(),
                    "revoked": False,
                    "scopes": ["jobs:create", "jobs:read", "jobs:cancel"],
                    "rate_limit": rl},
                "proyecto-delta": {  # sólo infer:text, sin vision
                    "token_sha256": hashlib.sha256(
                        TOKEN_DELTA.encode()).hexdigest(),
                    "revoked": False,
                    "scopes": ["jobs:create", "jobs:read", "jobs:cancel",
                               "infer:text"],
                    "rate_limit": rl},
            },
        }
        cls.tokens_path.write_text(json.dumps(config), encoding="utf-8")
        cls.backend = BackendFalso()
        cls.registry = TokenRegistry(cls.tokens_path)
        cls.dispatcher = FairQueueDispatcher()
        # jobs_dir inyectado en la construcción (MED-9): build_server
        # ya no crea un JobsManager con run/jobs por defecto.
        cls.server = build_server(
            ("127.0.0.1", 0),
            backend=cls.backend.url,
            auth_enabled=True,
            tokens_registry=cls.registry,
            dispatcher=cls.dispatcher,
            jobs_dir=cls.temp_dir / "jobs",
        )
        cls.puerto = cls.server.server_address[1]
        cls.hilo = threading.Thread(
            target=cls.server.serve_forever, daemon=True)
        cls.hilo.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.jobs_manager.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.backend.server_close()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def _post(self, cuerpo: dict, token: str, proyecto: str,
              crudo: bytes | None = None) -> tuple[int, dict]:
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.puerto}/jobs",
            data=crudo if crudo is not None
            else json.dumps(cuerpo).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "X-Project-ID": proyecto,
                "Idempotency-Key": f"bnd-{uuid.uuid4().hex[:12]}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_06_scope_de_modalidad_exigido(self):
        # gamma tiene jobs:create pero no infer:text -> 403, no 202
        cuerpo = {
            "operation": "infer_text",
            "payload": {"messages": [
                {"role": "user", "content": "analiza"}]},
        }
        status, res = self._post(cuerpo, TOKEN_GAMMA, "proyecto-gamma")
        self.assertEqual(status, 403)
        self.assertEqual(res["error"]["code"], "insufficient_scope")
        self.assertIn("infer:text", res["error"]["message"])

    def test_07_scope_de_modalidad_de_vision(self):
        # delta no tiene infer:vision: la operación infer_vision no se
        # admite aunque el payload sea de texto.
        cuerpo = {
            "operation": "infer_vision",
            "payload": {"messages": [
                {"role": "user", "content": "describe"}]},
        }
        status, res = self._post(cuerpo, TOKEN_DELTA, "proyecto-delta")
        self.assertEqual(status, 403)
        self.assertIn("infer:vision", res["error"]["message"])

    def test_08_payload_fuera_de_dialecto_rechazado(self):
        cuerpo = {
            "operation": "infer_text",
            "payload": {"prompt": "fuera del dialecto v2"},
        }
        status, res = self._post(cuerpo, TOKEN_ALPHA, "proyecto-alpha")
        self.assertEqual(status, 400, f"se admitió payload fuera del "
                                     f"dialecto: {res}")
        self.assertIn(res["error"]["code"],
                      {"unknown_field", "missing_messages"})

    def test_09_clave_duplicada_rechazada(self):
        crudo = (b'{"operation":"infer_text","payload":{"messages":'
                 b'[{"role":"user","content":"x"}]},"ttl_seconds":60,'
                 b'"ttl_seconds":90}')
        status, res = self._post(None, TOKEN_ALPHA, "proyecto-alpha",
                                 crudo=crudo)
        self.assertEqual(status, 400)
        self.assertEqual(res["error"]["code"], "invalid_json")
        self.assertIn("ttl_seconds", res["error"]["message"])

    def test_10_clave_duplicada_anidada_rechazada(self):
        crudo = (b'{"operation":"infer_text","payload":{"messages":'
                 b'[{"role":"user","content":"x"}],"max_tokens":5,'
                 b'"max_tokens":6}}')
        status, res = self._post(None, TOKEN_ALPHA, "proyecto-alpha",
                                 crudo=crudo)
        self.assertEqual(status, 400)
        self.assertIn("max_tokens", res["error"]["message"])

    def test_11_control_positivo_flujo_valido(self):
        cuerpo = {
            "operation": "infer_text",
            "payload": {"messages": [
                {"role": "user", "content": "hola frontera"}]},
        }
        status, res = self._post(cuerpo, TOKEN_ALPHA, "proyecto-alpha")
        self.assertEqual(status, 202, f"{res}")
        self.assertEqual(res["state"], "queued")

    def test_23_sobre_no_objeto_rechazado(self):
        # el sobre completo es dato no confiable: raíz no-objeto → 400.
        for crudo in (b"[]", b'"texto"', b"5"):
            status, res = self._post(None, TOKEN_ALPHA, "proyecto-alpha",
                                     crudo=crudo)
            self.assertEqual(status, 400, f"{crudo!r}: {res}")

    def test_24_ttl_invalido_rechazado(self):
        for ttl_malo in ("abc", [1], True, 59, 86401):
            cuerpo = {
                "operation": "infer_text",
                "payload": {"messages": [
                    {"role": "user", "content": "x"}]},
                "ttl_seconds": ttl_malo,
            }
            status, res = self._post(cuerpo, TOKEN_ALPHA, "proyecto-alpha")
            self.assertEqual(status, 400, f"ttl {ttl_malo!r}: {res}")


# --------------------------------- salida del backend antes de persistir
class SalidaBackendTests(unittest.TestCase):
    """Truncada o fuera de esquema: fallo explícito, nunca éxito."""

    SCHEMA = {
        "type": "object",
        "properties": {"respuesta": {"type": "string"}},
        "required": ["respuesta"],
    }

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_bnd_out_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def _manager_con_backend(self, respuesta, retardo_s=0.0):
        backend = BackendFalso(respuesta=respuesta, retardo_s=retardo_s)
        self.addCleanup(backend.server_close)
        manager = JobsManager(
            jobs_dir=self.temp_dir / "jobs", backend_url=backend.url)
        self.addCleanup(manager.stop)
        return manager

    def _crear(self, manager, payload, clave, ttl_seconds=3600):
        return manager.create_job(
            project_id="proyecto-alpha", operation="infer_text",
            payload=payload, idempotency_key=clave,
            ttl_seconds=ttl_seconds)

    def test_12_finish_reason_no_stop_es_fallo(self):
        truncada = {"choices": [{"message": {"content": "parcial"},
                                 "finish_reason": "length"}]}
        manager = self._manager_con_backend(truncada)
        payload = {"messages": [{"role": "user", "content": "largo"}]}
        status, res = self._crear(manager, payload, "bnd-trunc")
        self.assertEqual(status, 202)
        final = _esperar_terminal(manager, "proyecto-alpha", res["job_id"])
        self.assertEqual(final["state"], "failed",
                         f"salida truncada persistió como éxito: {final}")
        self.assertIsNotNone(final["error"])

    def test_13_salida_fuera_de_esquema_es_fallo(self):
        invalida = {"choices": [{"message": {"content": '{"otra": 1}'},
                                 "finish_reason": "stop"}]}
        manager = self._manager_con_backend(invalida)
        payload = {
            "messages": [{"role": "user", "content": "extrae"}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "respuesta", "schema": self.SCHEMA}},
        }
        status, res = self._crear(manager, payload, "bnd-schema-mal")
        self.assertEqual(status, 202)
        final = _esperar_terminal(manager, "proyecto-alpha", res["job_id"])
        self.assertEqual(final["state"], "failed",
                         f"salida fuera de esquema persistió: {final}")
        self.assertEqual(final["result"], None)

    def test_14_control_positivo_salida_valida(self):
        valida = {"choices": [{"message": {"content": '{"respuesta":"x"}'},
                               "finish_reason": "stop"}]}
        manager = self._manager_con_backend(valida)
        payload = {
            "messages": [{"role": "user", "content": "extrae"}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "respuesta", "schema": self.SCHEMA}},
        }
        status, res = self._crear(manager, payload, "bnd-schema-ok")
        self.assertEqual(status, 202)
        final = _esperar_terminal(manager, "proyecto-alpha", res["job_id"])
        self.assertEqual(final["state"], "succeeded")
        self.assertTrue(final["result"]["complete"])

    # test_15 (expires desde el terminal) se reescribió con reloj
    # falso, sin pausas reales, y vive como test_35 en
    # tests/test_jobs_despacho_i5.py (LOW-7; partida §3.4).


# --------------------------------- durabilidad de la admisión (BLOCKER-2)
class DurabilidadAdmisionTests(unittest.TestCase):
    """Sin 202 si la escritura no consta; sin registro, sin ejecución."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_bnd_dur_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.jobs_dir = self.temp_dir / "jobs"

    def _manager(self):
        backend = BackendFalso()
        self.addCleanup(backend.server_close)
        manager = JobsManager(jobs_dir=self.jobs_dir,
                              backend_url=backend.url)
        self.addCleanup(manager.stop)
        return manager, backend

    @staticmethod
    def _contador_fallo(funcion_real, fallar_en):
        estado = {"n": 0}
        cerrojo = threading.Lock()

        def envoltura(origen, destino):
            with cerrojo:
                estado["n"] += 1
                n = estado["n"]
            if n == fallar_en:
                raise OSError(f"fallo inyectado en la llamada {n}")
            return funcion_real(origen, destino)

        return envoltura

    def test_16_oserror_al_escribir_job_sin_202(self):
        manager, _ = self._manager()
        with mock.patch("os.replace",
                        self._contador_fallo(os.replace, 1)):
            status, res = manager.create_job(
                "proyecto-alpha", "infer_text",
                {"messages": [{"role": "user", "content": "x"}]},
                "bnd-dur-job")
        self.assertEqual(status, 500,
                         f"202 emitido sin escritura constatada: {res}")
        archivos = [p for p in (self.jobs_dir / "data").rglob("*")
                    if p.is_file()] \
            if (self.jobs_dir / "data").exists() else []
        self.assertEqual(archivos, [], "quedó un job sin admisión durable")

    def test_17_oserror_al_escribir_registro_sin_202(self):
        manager, _ = self._manager()
        with mock.patch("os.replace", os.replace), \
                mock.patch("os.link",
                           self._contador_fallo(os.link, 1)):
            status, res = manager.create_job(
                "proyecto-alpha", "infer_text",
                {"messages": [{"role": "user", "content": "x"}]},
                "bnd-dur-reg")
        self.assertEqual(status, 500,
                         f"202 emitido con registro no escrito: {res}")
        idem = [p for p in (self.jobs_dir / "idempotency").rglob("*")
                if p.is_file()] \
            if (self.jobs_dir / "idempotency").exists() else []
        jobs = [p for p in (self.jobs_dir / "data").rglob("*")
                if p.is_file()] \
            if (self.jobs_dir / "data").exists() else []
        self.assertEqual(idem, [], "registro fantasma tras fallo")
        self.assertEqual(jobs, [], "job huérfano tras fallo de registro")

    def test_18_job_en_cola_sin_registro_jamais_se_ejecuta(self):
        # caída entre las dos escrituras: job en disco, registro ausente
        _escribir_job_en_disco(
            self.jobs_dir, "proyecto-alpha", "job-huerfano-1",
            {"messages": [{"role": "user", "content": "marcador-huerfano"}]},
            clave="bnd-huerfano")
        archivo = (self.jobs_dir / "data" / "proyecto-alpha"
                   / "job-huerfano-1.json")
        # borrar sólo el registro: el commit nunca se completó
        hash_clave = hashlib.sha256(b"bnd-huerfano").hexdigest()
        (self.jobs_dir / "idempotency" / "proyecto-alpha"
         / f"{hash_clave}.json").unlink()
        self.assertTrue(archivo.exists())
        manager, backend = self._manager()  # startup_recover aquí
        final = _esperar_terminal(manager, "proyecto-alpha",
                                  "job-huerfano-1")
        self.assertEqual(final["state"], "failed")
        self.assertEqual(final["error"]["code"], "admission_unconfirmed")
        self.assertEqual(
            backend.cuenta_por_marcador("marcador-huerfano"), 0,
            "se ejecutó un job cuya admisión nunca se confirmó")


# ----------------------------- reclamo entre instancias y admisión (HIGH-1)
class ReclamoEntreInstanciasTests(unittest.TestCase):
    """Dos instancias, mismo data_dir: cada job se ejecuta una vez."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_bnd_clm_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.jobs_dir = self.temp_dir / "jobs"

    def test_19_segunda_instancia_falla_y_no_ejecuta_dos_veces(self):
        # D1 (Operador, 2026-11-08): una sola instancia por jobs_dir.
        # La premisa anterior (dos instancias conviviendo) quedó
        # prohibida: la segunda falla cerrada con el directorio en el
        # error y sin tocar los jobs; la primera ejecuta cada job
        # exactamente una vez.
        from jobs_manager import JobsDirOcupado

        marcadores = [f"marcador-doble-{i}" for i in range(3)]
        for i, marcador in enumerate(marcadores):
            _escribir_job_en_disco(
                self.jobs_dir, "proyecto-alpha", f"job-doble-{i}",
                {"messages": [{"role": "user", "content": marcador}]},
                clave=f"bnd-doble-{i}")
        backend = BackendFalso(retardo_s=0.3)
        self.addCleanup(backend.server_close)
        primera = JobsManager(jobs_dir=self.jobs_dir,
                              backend_url=backend.url)
        self.addCleanup(primera.stop)
        with self.assertRaises(JobsDirOcupado) as ctx:
            JobsManager(jobs_dir=self.jobs_dir, backend_url=backend.url)
        self.assertIn(str(self.jobs_dir), str(ctx.exception))
        for i, marcador in enumerate(marcadores):
            _esperar_terminal(primera, "proyecto-alpha",
                              f"job-doble-{i}", plazo=40.0)
        for marcador in marcadores:
            self.assertEqual(
                backend.cuenta_por_marcador(marcador), 1,
                f"ejecuciones de {marcador}: "
                f"{backend.cuenta_por_marcador(marcador)}")

    def test_20_worker_pasa_por_dispatcher_compartido(self):
        class DispatcherGrabador:
            def __init__(self):
                self.eventos = []
                self.cerrojo = threading.Lock()

            def acquire_slot(self, project_id, rl_config, timeout=None):
                with self.cerrojo:
                    self.eventos.append(("acquire", project_id))

            def release_slot(self, project_id):
                with self.cerrojo:
                    self.eventos.append(("release", project_id))

        _escribir_job_en_disco(
            self.jobs_dir, "proyecto-alpha", "job-adm-1",
            {"messages": [{"role": "user", "content": "marcador-adm"}]},
            clave="bnd-adm")
        try:
            grabador = DispatcherGrabador()
            backend = BackendFalso()
            self.addCleanup(backend.server_close)
            manager = JobsManager(
                jobs_dir=self.jobs_dir, backend_url=backend.url,
                dispatcher=grabador,
                rate_limit_lookup=lambda pid: {
                    "requests_per_minute": 600, "burst": 50,
                    "max_queue": 10, "queue_timeout_seconds": 5.0})
            self.addCleanup(manager.stop)
        except TypeError:
            self.fail("JobsManager no admite dispatcher compartido "
                      "(HIGH-1: presupuesto compartido con H/M)")
        _esperar_terminal(manager, "proyecto-alpha", "job-adm-1")
        self.assertEqual(
            backend.cuenta_por_marcador("marcador-adm"), 1)
        with grabador.cerrojo:
            self.assertIn(("acquire", "proyecto-alpha"),
                          grabador.eventos,
                          "el worker no adquirió admisión compartida")
            self.assertIn(("release", "proyecto-alpha"),
                          grabador.eventos)

    def test_26_worker_sobrevive_dispatcher_hostil(self):
        # regresión de la ronda adversarial: una excepción inesperada
        # del dispatcher no mata el worker ni fuga el flock del job.
        # Desde HIGH-4 el job además cierra failed durable (afirmado
        # en tests.test_jobs_intento2_i5.test_32); aquí se comprueba
        # que el flock quedó libre tomándolo directamente.
        import fcntl as _fcntl

        class DispatcherHostil:
            def acquire_slot(self, project_id, rl_config, timeout=None):
                raise RuntimeError("config de rate_limit corrupta")

            def release_slot(self, project_id):
                pass

        _escribir_job_en_disco(
            self.jobs_dir, "proyecto-alpha", "job-hostil-1",
            {"messages": [{"role": "user", "content": "marcador-hostil"}]},
            clave="bnd-hostil")
        backend = BackendFalso()
        self.addCleanup(backend.server_close)
        manager = JobsManager(
            jobs_dir=self.jobs_dir, backend_url=backend.url,
            dispatcher=DispatcherHostil(), rate_limit_lookup=lambda pid: {})
        self.addCleanup(manager.stop)
        _esperar_terminal(manager, "proyecto-alpha", "job-hostil-1",
                          plazo=10.0)
        self.assertTrue(manager._worker_thread.is_alive(),
                        "el worker murió por una excepción del dispatcher")
        self.assertEqual(backend.cuenta_por_marcador("marcador-hostil"), 0,
                         "se ejecutó un job sin admisión")
        lock_path = self.jobs_dir / "claims" / "job-hostil-1.lock"
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            _fcntl.flock(fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            self.fail("el flock del job quedó fugado")
        _fcntl.flock(fd, _fcntl.LOCK_UN)
        os.close(fd)


# -------------------------------------- retención y confidencialidad (HIGH-2)
class RetencionPermisosTests(unittest.TestCase):
    """Purga verificable al expirar, permisos 0600/0700 (§J)."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_bnd_ret_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.jobs_dir = self.temp_dir / "jobs"
        self.backend = BackendFalso()
        self.addCleanup(self.backend.server_close)
        self.manager = JobsManager(jobs_dir=self.jobs_dir,
                                   backend_url=self.backend.url)
        self.addCleanup(self.manager.stop)

    def _crear(self, clave):
        status, res = self.manager.create_job(
            "proyecto-alpha", "infer_text",
            {"messages": [{"role": "user",
                           "content": f"dato-privado-{clave}"}]},
            clave)
        self.assertEqual(status, 202)
        return res["job_id"]

    def test_21_purga_y_tombstone_al_expirar(self):
        job_id = self._crear("purga")
        archivo = (self.jobs_dir / "data" / "proyecto-alpha"
                   / f"{job_id}.json")
        # forzar vencimiento en disco
        job = json.loads(archivo.read_text(encoding="utf-8"))
        job["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        archivo.write_text(json.dumps(job), encoding="utf-8")
        status, res = self.manager.get_job("proyecto-alpha", job_id)
        self.assertEqual(status, 410)
        en_disco = json.loads(archivo.read_text(encoding="utf-8"))
        self.assertNotIn("payload", en_disco,
                         "la purga dejó el prompt del cliente en disco")
        self.assertNotIn("result", en_disco,
                         "la purga dejó el resultado en disco")
        self.assertEqual(en_disco.get("state"), "expired")

    def test_25_410_estable_y_delete_terminal_tras_purga(self):
        # regresión de la ronda adversarial: el 410 debe ser estable
        # (2º GET también 410) y DELETE sobre lo purgado es terminal.
        job_id = self._crear("estable")
        archivo = (self.jobs_dir / "data" / "proyecto-alpha"
                   / f"{job_id}.json")
        job = json.loads(archivo.read_text(encoding="utf-8"))
        job["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        archivo.write_text(json.dumps(job), encoding="utf-8")
        estados = [self.manager.get_job("proyecto-alpha", job_id)[0]
                   for _ in range(3)]
        self.assertEqual(estados, [410, 410, 410])
        status_del, res_del = self.manager.cancel_job(
            "proyecto-alpha", job_id)
        self.assertEqual(status_del, 200)
        self.assertEqual(res_del["cancellation_status"],
                         "already_terminal")

    def test_22_permisos_restringidos(self):
        job_id = self._crear("permisos")
        archivo = (self.jobs_dir / "data" / "proyecto-alpha"
                   / f"{job_id}.json")
        self.assertEqual(archivo.stat().st_mode & 0o777, 0o600,
                         "job JSON sin permisos 0600")
        for directorio in ("data", "idempotency"):
            modo = (self.jobs_dir / directorio).stat().st_mode & 0o777
            self.assertEqual(modo, 0o700,
                             f"{directorio} sin permisos 0700")
        modo_proyecto = (self.jobs_dir / "data" / "proyecto-alpha"
                         ).stat().st_mode & 0o777
        self.assertEqual(modo_proyecto, 0o700)
        registros = list((self.jobs_dir / "idempotency"
                          / "proyecto-alpha").glob("*.json"))
        for registro in registros:
            self.assertEqual(registro.stat().st_mode & 0o777, 0o600,
                             "registro de idempotencia sin 0600")


if __name__ == "__main__":
    unittest.main()
