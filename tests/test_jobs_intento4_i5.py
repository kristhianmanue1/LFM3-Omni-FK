#!/usr/bin/env python3
"""Pruebas del intento 4 del expediente fix-i5-jobs-frontera (Perfil J).

Propiedades exigidas por mandato-intento-4 sobre la revisión fresca de
la ronda 3 (revi5d), sin cambiar el diseño ni reabrir D1-D5. Los dos
controles del revisor (tests/test_review_revi5d.py del clon de esa
ronda) se copiaron como base de este RED y se adaptaron al estilo del
expediente; nada se ejecutó ni modificó en ese clon:

- [HIGH] Un 202 de reintento no puede dejar un job sin despacho:
  tras el doble fallo de retiro (registro y job siguen en disco), el
  reintento reconcilia bajo self.lock y encola UNA sola vez. El test
  reproduce los dos retiros fallidos de verdad y afirma el estado
  TERMINAL en disco, no sólo el 202 (test_50). test_51 es la guarda
  de «una sola vez»: verde por diseño contra HEAD, muerde si el fix
  reintroduce el doble encolado (precedente test_45/47b del intento
  3, declarado así en su RED).
- [MED] La purga con estado leído antes del lock no puede
  sobrescribir un running: get_job (test_53) y el barrido
  _purgar_expirados (test_52, variante sin sonda propia en la ronda
  3) recargan estado y vencimiento dentro de self.lock antes de
  purgar; _marcar_running revalida el TTL y deja constancia cuando el
  job ya estaba reclamado antes de vencer. Transición intercalada
  determinista, sin carreras de tiempo real.

Numeración continua la del intento 3 (tests 44-49). Backend falso en
puerto efímero y jobs_dir temporal siempre; nunca run/jobs ni 8091.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from unittest import mock

import sys
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "src"))

from jobs_manager import JobsManager
from jobs_storage import CommitTrasLinkError
from tests.test_jobs_boundary_i5 import BackendFalso, _esperar_terminal

ESTADOS_TERMINALES = {"succeeded", "failed", "cancelled", "expired"}


def _estado_en_disco(manager, project_id: str, job_id: str):
    job = manager.storage.load_job(project_id, job_id)
    return job.get("state") if job else None


def _esperar_terminal_en_disco(manager, project_id: str, job_id: str,
                               plazo: float = 5.0):
    """Poll del disco hasta un estado terminal; devuelve el último
    estado visto (el llamador afirma contra él)."""
    limite = time.monotonic() + plazo
    estado = None
    while time.monotonic() < limite:
        estado = _estado_en_disco(manager, project_id, job_id)
        if estado in ESTADOS_TERMINALES:
            break
        time.sleep(0.02)
    return estado


# ------------------ [HIGH] reintento 202 sin despacho (ronda 3)
class ReintentoReconciliadoTests(unittest.TestCase):
    """El reintento con la misma clave reconcilia registro y job bajo
    self.lock: un queued cuyo despacho no consta se encola UNA sola
    vez (test_50, base del control del revisor); el reintento sobre
    un job ya despachado no vuelve a encolarlo ni a ejecutarlo
    (test_51)."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_i4_red_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_50_reintento_tras_doble_fallo_despacha_y_termina(self):
        # Puerto 1: conexión rehusada al instante; un job despachado
        # termina en failed/execution_error de forma determinista.
        manager = JobsManager(jobs_dir=self.temp_dir / "jobs",
                              backend_url="http://127.0.0.1:1",
                              intervalo_barrido_s=999999.0)
        self.addCleanup(manager.stop)

        # Doble fallo de retiro REAL: el commit enlaza y luego
        # falla; ni el registro ni el job se pueden retirar (ambos
        # retiros fallan de verdad y quedan en disco).
        commit_real = manager.storage.commit_registro_idempotencia

        def commit_falla_tras_link(*args):
            commit_real(*args)
            raise CommitTrasLinkError("incertidumbre inyectada post-link")

        payload = {"messages": [{"role": "user", "content": "i4-doble"}]}
        with mock.patch.object(manager.storage,
                               "commit_registro_idempotencia",
                               commit_falla_tras_link), \
             mock.patch.object(manager.storage, "retirar_registro",
                               return_value=False), \
             mock.patch.object(manager.storage, "eliminar_job"):
            primera, res1 = manager.create_job(
                "proyecto-alpha", "infer_text", payload, "i4-doble-fallo")
        self.assertEqual(primera, 500)
        self.assertEqual(res1["error"]["code"], "storage_error")

        # Reintento con la misma clave: la pareja registro+job sigue
        # en disco y el job sigue queued SIN despacho constatable.
        segunda, vista = manager.create_job(
            "proyecto-alpha", "infer_text", payload, "i4-doble-fallo")
        self.assertEqual(segunda, 202)

        # El estado TERMINAL en disco, no sólo el 202 (mandato).
        estado = _esperar_terminal_en_disco(manager, "proyecto-alpha",
                                            vista["job_id"])
        self.assertEqual(
            estado, "failed",
            f"el 202 de reintento dejó el job en {estado!r}: solicitud "
            f"aceptada sin avance, sin despacho del worker")
        job = manager.storage.load_job("proyecto-alpha", vista["job_id"])
        self.assertEqual(job["error"]["code"], "execution_error")

    def test_51_reintento_sobre_despachado_no_duplica_encolado(self):
        # Guarda «una sola vez»: verde contra HEAD (hoy el reintento
        # no encola); muerde si el fix encola sin comprobar el
        # despacho. El worker se detiene tras TOMAR el job de la
        # cola: el reintento llega con el job queued y despachado.
        backend = BackendFalso()
        self.addCleanup(backend.server_close)
        manager = JobsManager(jobs_dir=self.temp_dir / "jobs",
                              backend_url=backend.url,
                              intervalo_barrido_s=999999.0)
        self.addCleanup(manager.stop)

        puerta = threading.Event()
        self.addCleanup(puerta.set)
        reclamo_real = manager._reclamar

        def reclamo_en_puerta(project_id, job_id):
            puerta.wait(5.0)
            return reclamo_real(project_id, job_id)

        payload = {"messages": [{"role": "user",
                                 "content": "i4-unica-vez"}]}
        with mock.patch.object(manager, "_reclamar", reclamo_en_puerta):
            primera, res1 = manager.create_job(
                "proyecto-alpha", "infer_text", payload, "i4-unica-vez")
            self.assertEqual(primera, 202)
            limite = time.monotonic() + 5.0
            while time.monotonic() < limite \
                    and manager.work_queue.qsize() > 0:
                time.sleep(0.02)
            self.assertEqual(
                manager.work_queue.qsize(), 0,
                "el worker no tomó el job de la cola; el test no "
                "ejercita la ventana del reintento")
            segunda, res2 = manager.create_job(
                "proyecto-alpha", "infer_text", payload, "i4-unica-vez")
            self.assertEqual(segunda, 202)
            self.assertEqual(res2["job_id"], res1["job_id"])
            self.assertEqual(
                manager.work_queue.qsize(), 0,
                "el reintento encoló una segunda vez un job ya "
                "despachado (mandato: una sola vez, sin doble "
                "encolado ni doble ejecución)")
            puerta.set()
        final = _esperar_terminal(manager, "proyecto-alpha",
                                  res1["job_id"])
        self.assertEqual(final["state"], "succeeded")
        self.assertEqual(
            backend.cuenta_por_marcador("i4-unica-vez"), 1,
            "el job se ejecutó más de una vez")


# -------- [MED] el barrido recarga bajo el lock antes de purgar
class BarridoRecargaBajoLockTests(unittest.TestCase):
    """_purgar_expirados no purga un job que pasó a running tras la
    lectura del snapshot: recarga estado y vencimiento dentro de
    self.lock antes de purgar (variante del hallazgo MED sin sonda
    propia en la ronda 3). Intercalación determinista."""

    def test_52_barrido_no_purga_running_intercalado(self):
        temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_i4_bar_"))
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        jobs_dir = temp_dir / "jobs"
        manager = JobsManager(jobs_dir=jobs_dir,
                              backend_url="http://127.0.0.1:1",
                              intervalo_barrido_s=999999.0)
        self.addCleanup(manager.stop)

        # Job queued ya vencido, escrito TRAS el arranque para que
        # la recuperación inicial no lo toque.
        archivo = (jobs_dir / "data" / "proyecto-alpha"
                   / "job-barrido.json")
        job = {
            "job_id": "job-barrido", "contract_version": "2",
            "project_id": "proyecto-alpha", "operation": "infer_text",
            "payload": {"messages": []}, "state": "queued",
            "created_at": "2026-01-01T00:00:00+00:00",
            "started_at": None, "completed_at": None,
            "expires_at": "2000-01-01T00:00:00+00:00",
            "result": None, "error": None,
        }
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_text(json.dumps(job), encoding="utf-8")

        # Intercalación determinista: al validar el vencimiento del
        # snapshot (antes de purgar y sin ningún lock), un "worker"
        # escribe running en disco. El barrido debe recargar bajo el
        # lock y no purgar; hoy purga el snapshot viejo.
        volcado = {"hecho": False}
        vencido_real = JobsManager._vencido

        def vencido_que_intercala(self_m, trab, ahora=None):
            if trab.get("job_id") == "job-barrido" \
                    and not volcado["hecho"]:
                volcado["hecho"] = True
                fresco = self_m.storage.load_job("proyecto-alpha",
                                                 "job-barrido")
                fresco["state"] = "running"
                fresco["started_at"] = "2026-01-01T00:00:01+00:00"
                self_m.storage.save_job(fresco)
            return vencido_real(self_m, trab, ahora)

        with mock.patch.object(JobsManager, "_vencido",
                               vencido_que_intercala):
            purgados = manager._purgar_expirados()
        en_disco = manager.storage.load_job("proyecto-alpha",
                                            "job-barrido")
        self.assertEqual(
            en_disco["state"], "running",
            f"el barrido purgó con un snapshot viejo y sobrescribió "
            f"el running: quedó {en_disco.get('state')!r}")
        self.assertEqual(
            purgados, 0,
            "el barrido cuenta como purgado un job que era running "
            "en el momento de purgar")


# --------- [MED] get_job no tombstonea un running nuevo
class GetJobNoTombstoneaRunningTests(unittest.TestCase):
    """get_job leyó un queued vencido antes del lock; el worker pasó
    el job a running bajo el mismo lock; el GET no puede purgar con
    el snapshot viejo (base del control del revisor de la ronda 3,
    con el TTL cruzado tras el reclamo)."""

    def test_53_get_no_tombstonea_running_nuevo(self):
        temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_i4_get_"))
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        jobs_dir = temp_dir / "jobs"
        manager = JobsManager(jobs_dir=jobs_dir,
                              backend_url="http://127.0.0.1:1",
                              intervalo_barrido_s=999999.0)
        self.addCleanup(manager.stop)

        job = {"job_id": "job-carrera",
               "project_id": "proyecto-alpha", "state": "queued",
               "expires_at": "2100-01-01T00:00:00+00:00"}
        manager.storage.save_job(job)
        fd_reclamo = manager._reclamar("proyecto-alpha", "job-carrera")
        self.assertIsNotNone(fd_reclamo)
        self.addCleanup(manager._soltar_reclamo, fd_reclamo)

        # El TTL cruza DESPUÉS del reclamo y antes del running: la
        # ventana exacta del hallazgo MED.
        job["expires_at"] = "2000-01-01T00:00:00+00:00"
        manager.storage.save_job(job)

        leyo = threading.Event()
        seguir = threading.Event()
        carga_real = manager._load_job

        def carga_pausada(project_id, job_id):
            snapshot = carga_real(project_id, job_id)
            if threading.current_thread() is hilo_get:
                leyo.set()
                self.assertTrue(seguir.wait(3))
            return snapshot

        resultado = {}
        with mock.patch.object(manager, "_load_job", carga_pausada):
            hilo_get = threading.Thread(
                target=lambda: resultado.update(
                    estado=manager.get_job("proyecto-alpha",
                                           "job-carrera")[0]))
            hilo_get.start()
            self.assertTrue(leyo.wait(3))
            self.assertTrue(
                manager._marcar_running("proyecto-alpha",
                                        "job-carrera"))
            seguir.set()
            hilo_get.join(3)
        self.assertFalse(hilo_get.is_alive())
        en_disco = carga_real("proyecto-alpha", "job-carrera")
        self.assertEqual(
            en_disco["state"], "running",
            f"un GET con snapshot viejo reemplazó el running del "
            f"job: quedó {en_disco.get('state')!r}")
        self.assertEqual(resultado.get("estado"), 410)


if __name__ == "__main__":
    unittest.main()
