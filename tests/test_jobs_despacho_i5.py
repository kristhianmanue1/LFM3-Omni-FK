#!/usr/bin/env python3
"""Pruebas del expediente fix-i5-despacho (Perfil J — tercera ola I5).

Cierra los hallazgos pendientes de la aceptación de riesgo residual
(docs/reviews/evidence/fix-i5-jobs-frontera/aceptacion-riesgo.md
§Seguimiento) y la disposición de la ronda 4, con RED primero (04 §3):

- [RESIDUAL-MED] Un OSError en la ventana desencolar → running
  persistido dejaba el job queued en disco, fuera de la cola y dentro
  de _en_cola: el reintento respondía 202 sin avance (202 eterno).
  Un test por transición de la ventana (claim, persistir running,
  admisión compartida y cierre por deadline), inyectando OSError;
  el siguiente reintento debe reencolar y ejecutar (o terminar en
  fallo explícito), jamás un 202 eterno.
- [LOW-1] _resolver_rival alineado con _asegurar_despacho: bajo D1 la
  vía create_job → FileExistsError es inalcanzable (una sola
  instancia por jobs_dir), así que la prueba alcanzable es la llamada
  directa con el estado que la rama debe reconciliar.
- [LOW-7] Reloj inyectable (constructor, valor real por defecto):
  barrido periódico (D4), purga de vencidos y deadline de admisión
  responden a un reloj falso, sin pausas reales. La reescritura de
  test_15 de la frontera (que esperaba 2.5 s reales) vive aquí como
  test_35: la retención §J cuenta desde el terminal, con deltas
  exactos.

Numeración continua la de la frontera (tests 01-26). Los helpers se
importan de tests.test_jobs_boundary_i5 (patrón del intento 4). Este
módulo se partió de la frontera por la contención de tamaño (§3.4 del
estándar, gate/v14): patrón de ola del repo, una por intento. Los
tests usan siempre data_dir temporal y backend falso en puerto
efímero; nunca run/jobs ni 8091.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from unittest import mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import sys
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "src"))

from gateway_core import ErrorV2
from jobs_manager import JobsManager, canonical_json_rfc8785
from jobs_storage import JobsStorage
from tests.test_jobs_boundary_i5 import (
    RESPUESTA_VALIDA,
    BackendFalso,
    _esperar_terminal,
    _escribir_job_en_disco,
)


# ------------------------- reloj falso y backend con puerta (LOW-7)
class RelojFalso:
    """Reloj de pared controlado por el test (LOW-7): datetime UTC que
    sólo avanza cuando el test lo ordena; sin pausas reales.
    Hilo-seguro: el worker del manager lo consulta."""

    def __init__(self, inicio: datetime | None = None):
        self._t = inicio or datetime.now(timezone.utc)
        self._cerrojo = threading.Lock()

    def avanzar(self, segundos: float) -> None:
        with self._cerrojo:
            self._t += timedelta(seconds=segundos)

    def __call__(self) -> datetime:
        with self._cerrojo:
            return self._t


class _ManejadorPuerta(BaseHTTPRequestHandler):
    """Responde 200 sólo cuando el test abre la puerta del servidor."""

    def do_POST(self):
        longitud = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(longitud)
        servidor = self.server
        servidor.puerta.wait(10.0)
        cuerpo = json.dumps(RESPUESTA_VALIDA).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, formato, *args):
        pass


class BackendPuerta(ThreadingHTTPServer):
    """Backend que RETIENE la respuesta hasta que el test abre la
    puerta: separa admisión y terminal sin pausas reales (LOW-7)."""

    daemon_threads = True

    def __init__(self):
        self.puerta = threading.Event()
        super().__init__(("127.0.0.1", 0), _ManejadorPuerta)
        self.hilo = threading.Thread(target=self.serve_forever,
                                     daemon=True)
        self.hilo.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"

    def abrir(self) -> None:
        self.puerta.set()


# ------------- ventana de despacho con OSError inyectado (RESIDUAL-MED)
class VentanaDespachoOSErrorTests(unittest.TestCase):
    """RESIDUAL-MED (aceptado por el Operador, 2026-11-08; seguimiento
    fix-i5-despacho). La prescripción: relectura bajo el lock; si el
    job sigue queued, sale de _en_cola para que el siguiente reintento
    lo reencole; si la relectura también falla, comportamiento actual
    (fail-closed). Cada test inyecta OSError en UNA transición de la
    ventana desencolar → running persistido."""

    MARCADOR = "med-ventana"

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_des_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.backend = BackendFalso()
        self.addCleanup(self.backend.server_close)
        # Barrido desactivado: la purga no debe resolver la ventana.
        self.manager = JobsManager(
            jobs_dir=self.temp_dir / "jobs",
            backend_url=self.backend.url, intervalo_barrido_s=999999.0)
        self.addCleanup(self.manager.stop)

    def _payload(self):
        return {"messages": [{"role": "user", "content": self.MARCADOR}]}

    def _esperar_reconciliacion(self, job_id, plazo=5.0) -> bool:
        """Poll del efecto del fix: el job abandonado sale de
        _en_cola (RED: nunca sale; el reintento sería un 202 eterno)."""
        limite = time.monotonic() + plazo
        while time.monotonic() < limite:
            if job_id not in self.manager._en_cola:
                return True
            time.sleep(0.02)
        return False

    def _afirmar_reencolado_y_ejecutado(self, payload, clave, job_id):
        """El siguiente reintento con la misma clave reencola y
        ejecuta exactamente una vez; jamás un 202 eterno."""
        self.assertTrue(
            self._esperar_reconciliacion(job_id),
            "el job abandonado sin running sigue en _en_cola: el "
            "siguiente reintento respondería 202 sin avance "
            "(RESIDUAL-MED)")
        status2, res2 = self.manager.create_job(
            "proyecto-alpha", "infer_text", payload, clave)
        self.assertEqual(status2, 202)
        self.assertEqual(res2["job_id"], job_id)
        final = _esperar_terminal(self.manager, "proyecto-alpha", job_id)
        self.assertEqual(final["state"], "succeeded")
        self.assertEqual(
            self.backend.cuenta_por_marcador(self.MARCADOR), 1,
            "el reintento no ejecutó el job (o lo ejecutó dos veces)")

    def test_27_oserror_en_el_claim_el_reintento_reencola(self):
        # Transición 1: os.open del cerrojo de reclamo falla; el
        # worker abandona un job ya retirado de la cola.
        payload = self._payload()
        apertura_real = os.open
        intentos = []
        inyeccion = {"activa": True}

        def apertura_inyectada(ruta, *args, **kwargs):
            intentos.append(str(ruta))
            if str(ruta).endswith(".lock") and inyeccion["activa"]:
                inyeccion["activa"] = False
                raise OSError("fallo inyectado al abrir el claim")
            return apertura_real(ruta, *args, **kwargs)

        with mock.patch("os.open", apertura_inyectada):
            status, res = self.manager.create_job(
                "proyecto-alpha", "infer_text", payload, "med-claim")
            self.assertEqual(status, 202)
            job_id = res["job_id"]
            # Constancia del paso por el claim ANTES de salir del
            # parche: la inyección se ejercitó de verdad.
            limite = time.monotonic() + 5.0
            while time.monotonic() < limite and not any(
                    r.endswith(".lock") for r in intentos):
                time.sleep(0.02)
        self.assertTrue(
            any(r.endswith(".lock") for r in intentos),
            "el worker no pasó por el claim; la inyección no se "
            "ejercitó (test inválido)")
        self._afirmar_reencolado_y_ejecutado(payload, "med-claim", job_id)

    def test_28_oserror_al_persistir_running_el_reintento_reencola(self):
        # Transición 2: save_job falla al persistir running (la ruta
        # :555 del expediente); el job queda queued en disco.
        payload = self._payload()
        save_real = JobsStorage.save_job
        fallado = {"hecho": False}

        def save_inyectado(storage, job_dict):
            if job_dict.get("state") == "running" \
                    and not fallado["hecho"]:
                fallado["hecho"] = True
                raise OSError("fallo inyectado al persistir running")
            return save_real(storage, job_dict)

        with mock.patch.object(JobsStorage, "save_job", save_inyectado):
            status, res = self.manager.create_job(
                "proyecto-alpha", "infer_text", payload, "med-running")
            self.assertEqual(status, 202)
            job_id = res["job_id"]
            limite = time.monotonic() + 5.0
            while time.monotonic() < limite and not fallado["hecho"]:
                time.sleep(0.02)
        self.assertTrue(
            fallado["hecho"],
            "el worker nunca intentó persistir running; la inyección "
            "no se ejercitó (test inválido)")
        self._afirmar_reencolado_y_ejecutado(payload, "med-running",
                                             job_id)

    def test_29_oserror_en_admision_el_reintento_reencola(self):
        # Transición 3: el dispatcher compartido falla con OSError al
        # conceder el slot; el job quedó desencolado y sin ejecutar.
        class DispatcherOSError:
            # Falla UNA sola vez: la propiedad exige que el reintento
            # progrese hasta la ejecución, no que la admisión siga
            # negándose para siempre.
            def __init__(self):
                self.fallado = False

            def acquire_slot(self, project_id, rl_config, timeout=None):
                if not self.fallado:
                    self.fallado = True
                    raise OSError("fallo inyectado en acquire_slot")

            def release_slot(self, project_id):
                pass

        payload = self._payload()
        self.manager.dispatcher = DispatcherOSError()
        status, res = self.manager.create_job(
            "proyecto-alpha", "infer_text", payload, "med-admision")
        self.assertEqual(status, 202)
        self._afirmar_reencolado_y_ejecutado(payload, "med-admision",
                                             res["job_id"])

    def test_30_oserror_al_cerrar_por_deadline_sin_202_eterno(self):
        # Transición 4 (guarda): el cierre por deadline no puede
        # persistir. Verde hoy: _cerrar descarta de _en_cola antes de
        # escribir y _deadline_admision_vencido reintenta por ciclo;
        # el test muerde si ese descarte desaparece. Reloj falso
        # (LOW-7): el deadline vence sin esperas reales.
        reloj = RelojFalso()

        class DispatcherNegativo:
            def acquire_slot(self, project_id, rl_config, timeout=None):
                raise ErrorV2(429, "rate_limit_error", "sin presupuesto")

            def release_slot(self, project_id):
                pass

        save_real = JobsStorage.save_job
        fallado = {"hecho": False}

        def save_inyectado(storage, job_dict):
            if job_dict.get("state") == "failed" \
                    and not fallado["hecho"]:
                fallado["hecho"] = True
                raise OSError(
                    "fallo inyectado al persistir admission_timeout")
            return save_real(storage, job_dict)

        manager = JobsManager(
            jobs_dir=self.temp_dir / "jobs-deadline",
            backend_url=self.backend.url, intervalo_barrido_s=999999.0,
            reloj=reloj, dispatcher=DispatcherNegativo(),
            rate_limit_lookup=lambda p: {})
        self.addCleanup(manager.stop)
        payload = self._payload()
        with mock.patch.object(JobsStorage, "save_job", save_inyectado):
            status, res = manager.create_job(
                "proyecto-alpha", "infer_text", payload, "med-deadline")
            self.assertEqual(status, 202)
            job_id = res["job_id"]
            reloj.avanzar(61.0)  # ESPERA_ADMISION_S = 60 (§J)
            limite = time.monotonic() + 10.0
            while time.monotonic() < limite and not fallado["hecho"]:
                time.sleep(0.05)
        self.assertTrue(
            fallado["hecho"],
            "el worker nunca intentó cerrar el job por deadline; la "
            "inyección no se ejercitó (test inválido)")
        limite = time.monotonic() + 15.0
        while True:
            _, vista = manager.get_job("proyecto-alpha", job_id)
            if vista.get("state") == "failed":
                break
            if time.monotonic() >= limite:
                self.fail(f"el job nunca cerró por deadline: {vista}")
            time.sleep(0.05)
        self.assertEqual(vista["error"]["code"], "admission_timeout")
        self.assertEqual(
            self.backend.cuenta_por_marcador(self.MARCADOR), 0,
            "un job vencido por deadline no debió ejecutarse")


# ---------------- LOW-1 (ronda 4): rival alineado con _asegurar_despacho
class RivalAlineadoTests(unittest.TestCase):
    """_resolver_rival (rama defensiva bajo D1) no puede responder 202
    sin despacho comprobable: se alinea con _asegurar_despacho."""

    def test_31_rival_queued_sin_despacho_reencola_y_ejecuta(self):
        temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_rival_"))
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        jobs_dir = temp_dir / "jobs"
        backend = BackendFalso()
        self.addCleanup(backend.server_close)
        manager = JobsManager(jobs_dir=jobs_dir, backend_url=backend.url,
                              intervalo_barrido_s=999999.0)
        self.addCleanup(manager.stop)
        payload = {"messages": [{"role": "user",
                                 "content": "marcador-rival"}]}
        # Rival queued en disco CON su registro, escrito TRAS el
        # arranque: no está en la cola ni en _en_cola.
        _escribir_job_en_disco(jobs_dir, "proyecto-alpha", "job-rival-1",
                               payload, clave="bnd-rival-01")
        hash_propio = hashlib.sha256(canonical_json_rfc8785(
            {"operation": "infer_text", "payload": payload})).hexdigest()
        status, res = manager._resolver_rival(
            "proyecto-alpha", "bnd-rival-01", hash_propio,
            "job-propio-descartado")
        self.assertEqual(status, 202, f"{res}")
        self.assertEqual(res["job_id"], "job-rival-1")
        self.assertIsNone(
            manager.storage.load_job("proyecto-alpha",
                                     "job-propio-descartado"),
            "el job propio del rival no fue descartado")
        limite = time.monotonic() + 5.0
        while time.monotonic() < limite \
                and "job-rival-1" not in manager._en_cola:
            time.sleep(0.02)
        self.assertIn(
            "job-rival-1", manager._en_cola,
            "el rival queued sin despacho no se encoló: 202 sin "
            "avance (LOW-1)")
        final = _esperar_terminal(manager, "proyecto-alpha",
                                  "job-rival-1")
        self.assertEqual(final["state"], "succeeded")
        self.assertEqual(backend.cuenta_por_marcador("marcador-rival"), 1)


# --------------- LOW-7: reloj inyectable (barrido, purga y deadline)
class RelojInyectableTests(unittest.TestCase):
    """El reloj es parámetro de constructor con el reloj real por
    defecto (LOW-7); los tests de tiempo usan un reloj falso sin
    pausas reales: barrido periódico (D4), purga de vencidos y
    deadline de admisión (§J) responden al reloj inyectado."""

    def _escribir_job_con_expira(self, manager, job_id, ttl_s=60):
        expira = (manager.reloj() + timedelta(seconds=ttl_s)).isoformat()
        job = {
            "job_id": job_id, "contract_version": "2",
            "project_id": "proyecto-alpha", "operation": "infer_text",
            "payload": {"messages": [{"role": "user",
                                      "content": "purga-reloj"}]},
            "state": "queued",
            "created_at": manager.reloj().isoformat(),
            "started_at": None, "completed_at": None,
            "expires_at": expira,
            "result": None, "error": None,
            "model_revision": "LiquidAI/LFM3-Omni-2B-GGUF",
        }
        manager.storage.save_job(job)

    def test_32_reloj_falso_gobierna_el_barrido(self):
        temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_reloj_"))
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        reloj = RelojFalso()
        manager = JobsManager(jobs_dir=temp_dir / "jobs",
                              backend_url="http://127.0.0.1:1",
                              reloj=reloj, intervalo_barrido_s=120.0)
        self.addCleanup(manager.stop)
        self._escribir_job_con_expira(manager, "job-reloj-1", ttl_s=60)
        # T0+61: el job ya venció pero el intervalo del barrido (120 s
        # de reloj falso) aún no: sin pausa real, no purga.
        reloj.avanzar(61.0)
        manager._barrido_si_toca()
        en_disco = manager.storage.load_job("proyecto-alpha",
                                            "job-reloj-1")
        self.assertEqual(en_disco["state"], "queued",
                         "el barrido no respetó el intervalo del "
                         "reloj inyectado")
        # T0+122 ≥ intervalo: el barrido purga el vencido.
        reloj.avanzar(61.0)
        manager._barrido_si_toca()
        en_disco = manager.storage.load_job("proyecto-alpha",
                                            "job-reloj-1")
        self.assertEqual(en_disco["state"], "expired",
                         "el barrido no respondió al reloj inyectado")
        self.assertNotIn("payload", en_disco,
                         "la purga dejó el prompt en disco")

    def test_33_reloj_falso_gobierna_la_purga(self):
        temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_reloj_"))
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        reloj = RelojFalso()
        manager = JobsManager(jobs_dir=temp_dir / "jobs",
                              backend_url="http://127.0.0.1:1",
                              reloj=reloj, intervalo_barrido_s=999999.0)
        self.addCleanup(manager.stop)
        self._escribir_job_con_expira(manager, "job-reloj-2", ttl_s=60)
        purgados = manager._purgar_expirados()  # en T0: no vencido
        self.assertEqual(purgados, 0)
        en_disco = manager.storage.load_job("proyecto-alpha",
                                            "job-reloj-2")
        self.assertEqual(en_disco["state"], "queued")
        reloj.avanzar(61.0)
        purgados = manager._purgar_expirados()
        self.assertEqual(purgados, 1,
                         "la purga no respondió al reloj inyectado")
        en_disco = manager.storage.load_job("proyecto-alpha",
                                            "job-reloj-2")
        self.assertEqual(en_disco["state"], "expired")

    def test_34_reloj_falso_gobierna_el_deadline_de_admision(self):
        temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_reloj_"))
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        reloj = RelojFalso()

        class DispatcherNegativo:
            def acquire_slot(self, project_id, rl_config, timeout=None):
                raise ErrorV2(429, "rate_limit_error", "sin presupuesto")

            def release_slot(self, project_id):
                pass

        manager = JobsManager(
            jobs_dir=temp_dir / "jobs", backend_url="http://127.0.0.1:1",
            reloj=reloj, intervalo_barrido_s=999999.0,
            dispatcher=DispatcherNegativo(),
            rate_limit_lookup=lambda p: {})
        self.addCleanup(manager.stop)
        status, res = manager.create_job(
            "proyecto-alpha", "infer_text",
            {"messages": [{"role": "user", "content": "deadline-reloj"}]},
            "bnd-deadline-reloj")
        self.assertEqual(status, 202)
        job_id = res["job_id"]
        # Control negativo con ciclos reales del worker y reloj
        # congelado: sin tiempo inyectado no hay cierre por deadline.
        claim = temp_dir / "jobs" / "claims" / f"{job_id}.lock"
        limite = time.monotonic() + 5.0
        while time.monotonic() < limite and not claim.exists():
            time.sleep(0.02)
        self.assertTrue(claim.exists(),
                        "el worker no cicló; el control no aplica")
        en_disco = manager.storage.load_job("proyecto-alpha", job_id)
        self.assertEqual(en_disco["state"], "queued",
                         "el deadline cerró sin que el reloj lo "
                         "alcanzara")
        creado = datetime.fromisoformat(en_disco["created_at"])
        plazo = datetime.fromisoformat(en_disco["admission_deadline"])
        self.assertEqual(
            (plazo - creado).total_seconds(), 60.0,
            "el deadline de admisión no se derivó del reloj inyectado")
        # Adelantar más allá del deadline (§J: 60 s de cola) sin
        # esperas reales: el worker cierra el job en failed.
        reloj.avanzar(61.0)
        limite = time.monotonic() + 15.0
        while True:
            _, vista = manager.get_job("proyecto-alpha", job_id)
            if vista.get("state") == "failed":
                break
            if time.monotonic() >= limite:
                self.fail(f"el deadline no cerró el job: {vista}")
            time.sleep(0.05)
        self.assertEqual(vista["error"]["code"], "admission_timeout")


# -------- §J vía reloj falso: la retención cuenta desde el terminal
class SalidaTerminalConRelojTests(unittest.TestCase):
    """Reescritura del test_15 de la frontera (LOW-7: tests de tiempo
    con reloj falso, sin pausas reales). Un backend con puerta retiene
    la respuesta para adelantar el tiempo de pared DURANTE la
    ejecución; los deltas son exactos."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_des_sal_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.reloj = RelojFalso()

    def test_35_expires_desde_el_terminal_con_reloj_falso(self):
        backend = BackendPuerta()
        self.addCleanup(backend.abrir)  # nunca dejar el handler colgado
        self.addCleanup(backend.server_close)
        manager = JobsManager(
            jobs_dir=self.temp_dir / "jobs", backend_url=backend.url,
            reloj=self.reloj)
        self.addCleanup(manager.stop)
        payload = {"messages": [{"role": "user", "content": "lento"}]}
        status, res = manager.create_job(
            "proyecto-alpha", "infer_text", payload, "bnd-expira",
            ttl_seconds=60)
        self.assertEqual(status, 202)
        # Esperar el running y adelantar el reloj ANTES del terminal:
        # el backend retiene la respuesta hasta abrir la puerta.
        limite = time.monotonic() + 10.0
        while True:
            _, vista = manager.get_job("proyecto-alpha", res["job_id"])
            if vista.get("state") == "running":
                break
            if time.monotonic() >= limite:
                self.fail(f"el job no llegó a running: {vista}")
            time.sleep(0.02)
        self.reloj.avanzar(10.0)
        backend.abrir()
        final = _esperar_terminal(manager, "proyecto-alpha", res["job_id"])
        dt_creado = datetime.fromisoformat(final["created_at"])
        dt_completado = datetime.fromisoformat(final["completed_at"])
        dt_expira = datetime.fromisoformat(final["expires_at"])
        self.assertEqual(
            (dt_completado - dt_creado).total_seconds(), 10.0,
            "el reloj falso no separó admisión y terminal: el test "
            "no ejercita la ventana")
        self.assertEqual(
            (dt_expira - dt_completado).total_seconds(), 60.0,
            "expires_at no cuenta exactamente desde el terminal (§J)")


if __name__ == "__main__":
    unittest.main()
