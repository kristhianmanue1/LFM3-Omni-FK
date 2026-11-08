#!/usr/bin/env python3
"""Pruebas del intento 3 del expediente fix-i5-jobs-frontera (Perfil J).

Propiedades exigidas por mandato-intento-3 sobre la revisión fresca de
la ronda 2 (revi5c), sin cambiar el diseño ni reabrir D1-D5:

- MED-1: startup_recover reconcilia cancellation_pending con una
  transición durable a failed (server_interrupted), junto a running.
- MED-2: control positivo de D2 — con un job running o
  cancellation_pending del proyecto, un segundo POST se admite (202);
  SPEC-i5:75 cuenta sólo queued. El test muerde si el conteo vuelve a
  los no terminales (sonda de reversión en red-intento-3.txt).
- MED-3: stop() sólo cierra el fd de instancia cuando el worker
  terminó de verdad; vivo tras el plazo, fail-closed: el jobs_dir
  sigue tomado (JobsDirOcupado para una segunda instancia) y el motivo
  queda en stderr.
- LOW-4: el flock del jobs_dir bifurca por errno — EWOULDBLOCK/EAGAIN
  es otra instancia; el resto (p. ej. ENOLCK), un sistema de archivos
  sin cerrojos; ambos fail-closed, nombrando directorio y causa.
- LOW-5: la rama irretirable tras os.link responde 500 storage_error
  (nunca 202 sin confirmación durable) y el reintento reconcilia por
  la vía del huérfano.
- LOW-6: la purga de get_job corre bajo self.lock, sin intercalarse
  con la transición running del worker.

LOW-7 (reloj inyectable) queda como seguimiento por mandato; sin test
aquí. Numeración continua la del intento 2 (tests 44-49). Backend
falso en puerto efímero y jobs_dir temporal siempre; nunca run/jobs
ni 8091.
"""

from __future__ import annotations

import errno
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest import mock

import sys
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "src"))

from jobs_manager import JobsDirOcupado, JobsManager
from jobs_storage import JobsStorage
from tests.test_jobs_boundary_i5 import (
    BackendFalso, _escribir_job_en_disco, _esperar_terminal,
)


def _forzar_estado(jobs_dir: Path, project_id: str, job_id: str,
                   estado: str) -> Path:
    """Reescribe el estado de un job en disco; devuelve su archivo."""
    archivo = jobs_dir / "data" / project_id / f"{job_id}.json"
    job = json.loads(archivo.read_text(encoding="utf-8"))
    job["state"] = estado
    archivo.write_text(json.dumps(job), encoding="utf-8")
    return archivo


# -------------------- MED-1: reconciliación de cancellation_pending
class RecuperacionArranqueTests(unittest.TestCase):
    """startup_recover fail-closed: running y cancellation_pending
    pasan a failed (server_interrupted); el estado se afirma en disco."""

    def test_44_cancellation_pending_a_failed_en_arranque(self):
        temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_i3_rec_"))
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        jobs_dir = temp_dir / "jobs"
        _escribir_job_en_disco(
            jobs_dir, "proyecto-alpha", "job-cancel-crash",
            {"messages": [{"role": "user", "content": "x"}]},
            clave="i3-cancel-crash")
        archivo = _forzar_estado(jobs_dir, "proyecto-alpha",
                                 "job-cancel-crash", "cancellation_pending")
        backend = BackendFalso()
        self.addCleanup(backend.server_close)
        manager = JobsManager(jobs_dir=jobs_dir, backend_url=backend.url)
        self.addCleanup(manager.stop)
        en_disco = json.loads(archivo.read_text(encoding="utf-8"))
        self.assertEqual(
            en_disco.get("state"), "failed",
            "un crash durante la ventana de cancelación dejó el job "
            "sin reconciliar al arrancar (§J: cancellation_pending -> "
            "cancelled/failed)")
        self.assertEqual(en_disco.get("error", {}).get("code"),
                         "server_interrupted")


# ------------------------- MED-2: control positivo de D2 (SPEC-i5:75)
class AdmisionSoloCuentaQueuedTests(unittest.TestCase):
    """Con un job running o cancellation_pending del proyecto, un
    segundo POST se admite (202): SPEC-i5:75 cuenta sólo queued. Rojo
    si el conteo vuelve a incluir estados no terminales."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_i3_d2_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.jobs_dir = self.temp_dir / "jobs"
        self.backend = BackendFalso()
        self.addCleanup(self.backend.server_close)
        self.manager = JobsManager(jobs_dir=self.jobs_dir,
                                   backend_url=self.backend.url)
        self.addCleanup(self.manager.stop)

    def test_45_job_en_curso_no_bloquea_admision(self):
        for estado in ("running", "cancellation_pending"):
            with self.subTest(estado=estado):
                job_id = f"job-en-{estado}"
                _escribir_job_en_disco(
                    self.jobs_dir, "proyecto-alpha", job_id,
                    {"messages": [{"role": "user", "content": estado}]},
                    clave=f"i3-{estado}")
                _forzar_estado(self.jobs_dir, "proyecto-alpha",
                               job_id, estado)
                status, res = self.manager.create_job(
                    "proyecto-alpha", "infer_text",
                    {"messages": [{"role": "user",
                                   "content": f"post-{estado}"}]},
                    f"i3-post-{estado}")
                self.assertEqual(
                    status, 202,
                    f"con un job {estado} del proyecto, el POST debía "
                    f"admitirse (SPEC-i5:75 cuenta sólo queued): "
                    f"{status} {res}")
                final = _esperar_terminal(self.manager, "proyecto-alpha",
                                          res["job_id"])
                self.assertEqual(final["state"], "succeeded")


# --------------- MED-3: stop() no libera el jobs_dir con worker vivo
class StopConWorkerVivoTests(unittest.TestCase):
    """stop() cierra el fd de instancia sólo cuando el hilo del worker
    terminó de verdad; vivo tras el plazo, el jobs_dir queda tomado
    (fail-closed) y el motivo queda constanciado en stderr."""

    def test_46_segunda_instancia_bloqueada_mientras_vive_el_worker(self):
        temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_i3_stp_"))
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        jobs_dir = temp_dir / "jobs"
        backend = BackendFalso(retardo_s=4.0)
        self.addCleanup(backend.server_close)
        manager = JobsManager(jobs_dir=jobs_dir, backend_url=backend.url)
        status, res = manager.create_job(
            "proyecto-alpha", "infer_text",
            {"messages": [{"role": "user", "content": "lento-i3"}]},
            "i3-stop-lento")
        self.assertEqual(status, 202)
        archivo = (jobs_dir / "data" / "proyecto-alpha"
                   / f"{res['job_id']}.json")
        en_disco = None
        limite = time.monotonic() + 5.0
        while time.monotonic() < limite:
            en_disco = json.loads(archivo.read_text(encoding="utf-8"))
            if en_disco.get("state") == "running":
                break
            time.sleep(0.05)
        self.assertEqual(en_disco.get("state"), "running",
                         "el job no llegó a running contra el backend "
                         "lento; el test no ejercita la ventana")

        manager.stop(timeout=0.3)  # el worker sigue ejecutando el job
        self.assertTrue(manager._worker_thread.is_alive(),
                        "el worker terminó antes del plazo; sube el "
                        "retardo del backend")
        with self.assertRaises(JobsDirOcupado):
            JobsManager(jobs_dir=jobs_dir, backend_url=backend.url)

        # El worker termina (el backend responde) y entonces sí se
        # puede liberar el cerrojo: el directorio queda tomado
        # exactamente hasta que el worker deja de existir.
        limite = time.monotonic() + 20.0
        while time.monotonic() < limite \
                and manager._worker_thread.is_alive():
            time.sleep(0.1)
        self.assertFalse(manager._worker_thread.is_alive(),
                         "el worker no terminó tras el backend lento")
        manager.stop()
        segunda = JobsManager(jobs_dir=jobs_dir, backend_url=backend.url)
        self.addCleanup(segunda.stop)
        final = json.loads(archivo.read_text(encoding="utf-8"))
        self.assertIn(final.get("state"), ("succeeded", "failed"))


# ------------------------ LOW-4: diagnóstico del flock por errno
class DiagnosticoCerrojoInstanciaTests(unittest.TestCase):
    """El OSError del flock bifurca por errno: EWOULDBLOCK/EAGAIN es
    otra instancia; ENOLCK (u otro) es un sistema de archivos sin
    cerrojos. Ambos fallan cerrados, con directorio y causa real."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_i3_lck_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.jobs_dir = self.temp_dir / "jobs"

    def test_47_errno_distingue_ocupado_de_no_soportado(self):
        # ENOLCK: cerrojo no soportado por el sistema de archivos.
        fallo = OSError(errno.ENOLCK, "No locks available")
        with mock.patch("fcntl.flock", side_effect=fallo):
            with self.assertRaises(JobsDirOcupado) as ctx:
                JobsStorage(self.jobs_dir).tomar_cerrojo_instancia()
        mensaje = str(ctx.exception)
        self.assertIn(str(self.jobs_dir), mensaje,
                      "el error no nombra el jobs_dir en disputa")
        self.assertIn("sistema de archivos", mensaje,
                      f"ENOLCK no se diagnosticó como FS sin cerrojos: "
                      f"{mensaje}")
        self.assertNotIn("otra instancia", mensaje,
                         "ENOLCK diagnosticado como instancia ocupada")

        # EWOULDBLOCK: sí es otra instancia.
        ocupado = OSError(errno.EWOULDBLOCK,
                          "Resource temporarily unavailable")
        with mock.patch("fcntl.flock", side_effect=ocupado):
            with self.assertRaises(JobsDirOcupado) as ctx:
                JobsStorage(self.temp_dir / "jobs2") \
                    .tomar_cerrojo_instancia()
        self.assertIn("otra instancia", str(ctx.exception))

    def test_47b_enolck_es_fail_closed_en_el_arranque(self):
        # Con ENOLCK no arranca worker ni recuperación: un queued
        # preexistente queda intacto en disco.
        _escribir_job_en_disco(
            self.jobs_dir, "proyecto-alpha", "job-encolado",
            {"messages": [{"role": "user", "content": "x"}]},
            clave="i3-enolck")
        archivo = (self.jobs_dir / "data" / "proyecto-alpha"
                   / "job-encolado.json")
        fallo = OSError(errno.ENOLCK, "No locks available")
        with mock.patch("fcntl.flock", side_effect=fallo):
            with self.assertRaises(JobsDirOcupado):
                JobsManager(jobs_dir=self.jobs_dir,
                            backend_url="http://127.0.0.1:1")
        en_disco = json.loads(archivo.read_text(encoding="utf-8"))
        self.assertEqual(en_disco.get("state"), "queued",
                         "el arranque sin cerrojo tocó el estado de un "
                         "job sin ser la instancia autorizada")


# ----------------- LOW-5: rama irretirable tras link responde 500
class RamaIrretirableTests(unittest.TestCase):
    """CommitTrasLinkError con registro irretirable: 500 storage_error
    (nunca 202 sobre durabilidad no confirmada); el reintento con la
    misma clave reconcilia por la vía del huérfano."""

    def test_48_irretirable_tras_link_es_500_y_reintenta(self):
        temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_i3_irr_"))
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        jobs_dir = temp_dir / "jobs"
        backend = BackendFalso()
        self.addCleanup(backend.server_close)
        manager = JobsManager(jobs_dir=jobs_dir, backend_url=backend.url)
        self.addCleanup(manager.stop)
        payload = {"messages": [{"role": "user", "content": "irr-i3"}]}

        # fsync n.º 4 = directorio de idempotency, post-link; y el
        # registro no se puede retirar (unlink falla): la rama de
        # durabilidad no confirmada del commit (hallazgo 5, ronda 2).
        estado = {"n": 0}
        fsync_real = os.fsync

        def fsync_falla_en_4(fd):
            estado["n"] += 1
            if estado["n"] == 4:
                raise OSError("fallo inyectado en fsync 4")
            return fsync_real(fd)

        with mock.patch("os.fsync", fsync_falla_en_4), \
                mock.patch.object(manager.storage, "retirar_registro",
                                  return_value=False):
            status1, res1 = manager.create_job(
                "proyecto-alpha", "infer_text", payload, "i3-irretirable")
        self.assertEqual(
            status1, 500,
            f"202 apoyado en durabilidad no confirmada: {status1} "
            f"{res1}")
        self.assertEqual(res1["error"]["code"], "storage_error")

        # El reintento reconcilia por la vía del huérfano: registro
        # presente, job retirado, readmisión limpia.
        status2, res2 = manager.create_job(
            "proyecto-alpha", "infer_text", payload, "i3-irretirable")
        self.assertEqual(status2, 202,
                         f"la clave quedó bloqueada tras el fallo: "
                         f"{status2} {res2}")
        final = _esperar_terminal(manager, "proyecto-alpha",
                                  res2["job_id"])
        self.assertEqual(final["state"], "succeeded")


# ---------------------- LOW-6: purga de get_job bajo self.lock
class PurgaGetJobBajoLockTests(unittest.TestCase):
    """El tombstone de un vencido en get_job corre bajo self.lock: no
    puede intercalarse con la transición running del worker."""

    def test_49_purga_de_get_job_toma_self_lock(self):
        temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_i3_pgl_"))
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        jobs_dir = temp_dir / "jobs"
        backend = BackendFalso()
        self.addCleanup(backend.server_close)
        # Barrido desactivado: la única purga posible es la de get_job.
        manager = JobsManager(jobs_dir=jobs_dir,
                              backend_url=backend.url,
                              intervalo_barrido_s=999999.0)
        self.addCleanup(manager.stop)
        status, res = manager.create_job(
            "proyecto-alpha", "infer_text",
            {"messages": [{"role": "user", "content": "pgl-i3"}]},
            "i3-purga-lock")
        self.assertEqual(status, 202)
        _esperar_terminal(manager, "proyecto-alpha", res["job_id"])
        archivo = (jobs_dir / "data" / "proyecto-alpha"
                   / f"{res['job_id']}.json")
        job = json.loads(archivo.read_text(encoding="utf-8"))
        job["expires_at"] = "2000-01-01T00:00:00+00:00"
        archivo.write_text(json.dumps(job), encoding="utf-8")

        visto = {}
        purga_real = JobsManager._purgar_job

        def purga_espia(self_m, job_dict):
            visto["locked"] = self_m.lock.locked()
            return purga_real(self_m, job_dict)

        with mock.patch.object(JobsManager, "_purgar_job", purga_espia):
            status_get, _ = manager.get_job("proyecto-alpha",
                                            res["job_id"])
        self.assertEqual(status_get, 410)
        self.assertTrue(visto.get("locked"),
                        "la purga de get_job corre fuera de self.lock "
                        "(puede intercalarse con _marcar_running)")


if __name__ == "__main__":
    unittest.main()
