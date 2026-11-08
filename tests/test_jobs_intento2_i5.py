#!/usr/bin/env python3
"""Pruebas del intento 2 del expediente fix-i5-jobs-frontera (Perfil J).

Propiedades nuevas exigidas por mandato-intento-2 sobre la revisión
fresca de la ronda 1, con decisiones D1-D5 del Operador (2026-11-08):

- D1: una sola instancia por jobs_dir; la segunda falla cerrada,
  sin worker ni recuperación; admisiones concurrentes con claves
  distintas dan exactamente un 202 (HIGH-2/3/7).
- BLOCKER-1: el commit del registro es recuperable — un fallo tras
  os.link (p. ej. fsync del directorio) no bloquea el reintento; un
  registro huérfano se reconcilia al reintentar.
- HIGH-4: una excepción no ErrorV2 deja el job en failed durable con
  motivo (worker_internal_error), no en queued.
- HIGH-5: deadline de admisión persistido por job; agotado, el job
  pasa a failed (admission_timeout); saturación sin esperas infinitas.
- HIGH-6/D4: barrido periódico dentro del bucle del worker (sin hilo
  nuevo), temporales huérfanos (*.tmp.*) y claims fuera bajo el
  cerrojo de instancia; una purga que falla es observable y reintenta.
- MED-8: operation no cadena responde 400 controlado.
- MED-9: build_server sin jobs_dir no construye JobsManager ni crea
  run/jobs; /jobs responde 501 hasta asignar uno.

Numeración continua la del boundary (tests 27-39). Backend falso en
puerto efímero y jobs_dir temporal siempre; nunca run/jobs ni 8091.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import fcntl
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
import urllib.error
import urllib.request
import uuid

import sys
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "src"))

from gateway_auth import FairQueueDispatcher, TokenRegistry
from gateway_http import build_server
from jobs_manager import JobsManager
from tests.test_jobs_boundary_i5 import (
    BackendFalso, _escribir_job_en_disco, _esperar_terminal,
)


TOKEN_ALPHA = "alpha-intento2-token-for-i5-32chars"
RL_SATURADO = {  # token bucket que nunca concede: el job queda queued
    "requests_per_minute": 0, "burst": 0, "max_queue": 10,
    "queue_timeout_seconds": 5.0,
}


def _dispatcher_que_nunca_admite():
    return FairQueueDispatcher()


# ------------------------------------------- D1: una instancia por jobs_dir
class InstanciaUnicaTests(unittest.TestCase):
    """HIGH-2/3/7: el cerrojo de instancia cierra la concurrencia
    entre procesos y las admisiones concurrentes quedan acotadas."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_i2_ins_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.jobs_dir = self.temp_dir / "jobs"
        self.backend = BackendFalso()
        self.addCleanup(self.backend.server_close)

    def test_27_segunda_instancia_falla_cerrada(self):
        manager = JobsManager(jobs_dir=self.jobs_dir,
                              backend_url=self.backend.url)
        self.addCleanup(manager.stop)
        # Un running vivo de la primera instancia NO debe ser tocado
        # por el arranque de la segunda (hallazgo 3 de la revisión).
        _escribir_job_en_disco(
            self.jobs_dir, "proyecto-alpha", "job-vivo-r1",
            {"messages": [{"role": "user", "content": "x"}]},
            clave="i2-vivo-r1")
        archivo = (self.jobs_dir / "data" / "proyecto-alpha"
                   / "job-vivo-r1.json")
        job = json.loads(archivo.read_text(encoding="utf-8"))
        job["state"] = "running"
        archivo.write_text(json.dumps(job), encoding="utf-8")

        with self.assertRaises(RuntimeError) as ctx:
            JobsManager(jobs_dir=self.jobs_dir,
                        backend_url=self.backend.url)
        self.assertIn(str(self.jobs_dir), str(ctx.exception),
                      "el error no nombra el jobs_dir en disputa")
        tras_fallo = json.loads(archivo.read_text(encoding="utf-8"))
        self.assertEqual(tras_fallo.get("state"), "running",
                         "la segunda instancia ejecutó la recuperación "
                         "sin ser la instancia autorizada")

    def test_28_admisiones_concurrentes_un_solo_202(self):
        manager = JobsManager(
            jobs_dir=self.jobs_dir, backend_url=self.backend.url,
            dispatcher=_dispatcher_que_nunca_admite(),
            rate_limit_lookup=lambda pid: dict(RL_SATURADO))
        self.addCleanup(manager.stop)
        resultados: list[tuple[int, str]] = []
        cerrojo = threading.Lock()
        barrera = threading.Barrier(6)

        def admitir(i: int):
            barrera.wait(timeout=5.0)
            status, res = manager.create_job(
                "proyecto-alpha", "infer_text",
                {"messages": [{"role": "user", "content": f"conc-{i}"}]},
                f"i2-conc-{i}")
            with cerrojo:
                resultados.append((status, json.dumps(res)))

        hilos = [threading.Thread(target=admitir, args=(i,))
                 for i in range(6)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(timeout=10.0)
        self.assertEqual(len(resultados), 6)
        aceptados = [r for r in resultados if r[0] == 202]
        rechazados = [r for r in resultados if r[0] == 429]
        self.assertEqual(len(aceptados), 1,
                         f"esperaba exactamente un 202: {resultados}")
        self.assertEqual(len(rechazados), 5)
        for _, cuerpo in rechazados:
            self.assertIn("queue_limit_per_project_exceeded", cuerpo)


# -------------------------------- BLOCKER-1: commit del registro recuperable
class CommitRecuperableTests(unittest.TestCase):
    """Un fallo en cualquier paso tras os.link deja la admisión
    reconciliable: el reintento con la misma clave siempre funciona."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_i2_com_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.jobs_dir = self.temp_dir / "jobs"
        self.backend = BackendFalso()
        self.addCleanup(self.backend.server_close)
        self.payload = {"messages": [{"role": "user", "content": "bk1"}]}

    def _manager(self):
        manager = JobsManager(jobs_dir=self.jobs_dir,
                              backend_url=self.backend.url)
        self.addCleanup(manager.stop)
        return manager

    @staticmethod
    def _fallo_en_llamada(funcion_real, indice_fallo):
        """Envoltura de aridad 1 (fsync) que falla en la llamada n."""
        estado = {"n": 0}
        cerrojo = threading.Lock()

        def envoltura(fd):
            with cerrojo:
                estado["n"] += 1
                n = estado["n"]
            if n == indice_fallo:
                raise OSError(f"fallo inyectado en fsync {n}")
            return funcion_real(fd)

        return envoltura

    @staticmethod
    def _fallo_en_par(funcion_real, indice_fallo):
        """Envoltura de aridad 2 (replace/link) que falla en la n."""
        estado = {"n": 0}
        cerrojo = threading.Lock()

        def envoltura(origen, destino):
            with cerrojo:
                estado["n"] += 1
                n = estado["n"]
            if n == indice_fallo:
                raise OSError(f"fallo inyectado en la llamada {n}")
            return funcion_real(origen, destino)

        return envoltura

    def _crear(self, manager, clave):
        return manager.create_job("proyecto-alpha", "infer_text",
                                  self.payload, clave)

    def test_29_fsync_post_link_no_bloquea_reintento(self):
        # Secuencia de fsync en create_job: (1) tmp del job,
        # (2) dir de data, (3) tmp del registro, (4) dir de idempotency
        # — post-link. Fallar ahí es el BLOCKER-1 de la revisión.
        manager = self._manager()
        with mock.patch("os.fsync",
                        self._fallo_en_llamada(os.fsync, 4)):
            status, res = self._crear(manager, "i2-bk1")
        self.assertEqual(status, 500, f"esperaba 500 con fallo durable: "
                                      f"{status} {res}")
        # El reintento con la misma clave debe funcionar, no 410.
        status2, res2 = self._crear(manager, "i2-bk1")
        self.assertEqual(status2, 202,
                         f"reintento bloqueado tras fallo post-link: "
                         f"{status2} {res2}")
        status_get, res_get = manager.get_job(
            "proyecto-alpha", res2["job_id"])
        self.assertEqual(status_get, 200)
        jobs_en_disco = [p for p in (self.jobs_dir / "data").rglob("*.json")]
        self.assertEqual(len(jobs_en_disco), 1,
                         "quedaron restos de la admisión fallida")

    def test_30_registro_huerfano_reintento_funciona(self):
        # Crash entre el link y cualquier reconciliación: registro
        # vivo que apunta a un job inexistente. El reintento debe
        # readmitir, no responder 410 para siempre.
        manager = self._manager()
        _escribir_job_en_disco(
            self.jobs_dir, "proyecto-alpha", "job-fantasma",
            self.payload, clave="i2-fantasma")
        (self.jobs_dir / "data" / "proyecto-alpha"
         / "job-fantasma.json").unlink()  # sólo queda el registro
        status, res = self._crear(manager, "i2-fantasma")
        self.assertEqual(status, 202,
                         f"registro huérfano bloqueó la admisión: "
                         f"{status} {res}")
        status_get, _ = manager.get_job("proyecto-alpha", res["job_id"])
        self.assertEqual(status_get, 200)

    def test_31_inyeccion_de_fallo_en_cada_paso(self):
        # Cada paso de escritura falla una vez; en todos los casos el
        # reintento con la misma clave funciona y el job queda legible.
        casos = [("fsync", 1), ("fsync", 2), ("fsync", 3), ("fsync", 4),
                 ("replace", 1), ("link", 1)]
        for tipo, indice in casos:
            with self.subTest(paso=f"{tipo}#{indice}"):
                sub_dir = self.temp_dir / f"c_{tipo}_{indice}"
                manager = JobsManager(jobs_dir=sub_dir,
                                      backend_url=self.backend.url)
                self.addCleanup(manager.stop)
                if tipo == "fsync":
                    parche = mock.patch(
                        "os.fsync", self._fallo_en_llamada(os.fsync,
                                                           indice))
                elif tipo == "replace":
                    parche = mock.patch(
                        "os.replace",
                        self._fallo_en_par(os.replace, indice))
                else:
                    parche = mock.patch(
                        "os.link", self._fallo_en_par(os.link, indice))
                with parche:
                    status1, res1 = manager.create_job(
                        "proyecto-alpha", "infer_text", self.payload,
                        "i2-paso")
                self.assertIn(status1, (202, 500),
                              f"respuesta inesperada: {status1} {res1}")
                status2, res2 = manager.create_job(
                    "proyecto-alpha", "infer_text", self.payload,
                    "i2-paso")
                self.assertEqual(status2, 202,
                                 f"reintento roto tras {tipo}#{indice}: "
                                 f"{status2} {res2}")
                status_get, _ = manager.get_job(
                    "proyecto-alpha", res2["job_id"])
                self.assertEqual(status_get, 200)


# ------------------------------ HIGH-4: excepción no ErrorV2 es durable
class WorkerRobustoTests(unittest.TestCase):
    """El defecto inesperado del dispatcher cierra el job en failed
    con motivo; el worker sigue vivo."""

    def test_32_runtimeerror_deja_job_failed_durable(self):
        class DispatcherHostil:
            def acquire_slot(self, project_id, rl_config, timeout=None):
                raise RuntimeError("config de rate_limit corrupta")

            def release_slot(self, project_id):
                pass

        temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_i2_wrk_"))
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        jobs_dir = temp_dir / "jobs"
        _escribir_job_en_disco(
            jobs_dir, "proyecto-alpha", "job-hostil-2",
            {"messages": [{"role": "user", "content": "marcador-h2"}]},
            clave="i2-hostil")
        backend = BackendFalso()
        self.addCleanup(backend.server_close)
        manager = JobsManager(
            jobs_dir=jobs_dir, backend_url=backend.url,
            dispatcher=DispatcherHostil(), rate_limit_lookup=lambda pid: {})
        self.addCleanup(manager.stop)
        final = _esperar_terminal(manager, "proyecto-alpha",
                                  "job-hostil-2", plazo=10.0)
        self.assertEqual(final["state"], "failed",
                         "el job quedó admitido sin cierre durable")
        self.assertEqual(final["error"]["code"], "worker_internal_error")
        self.assertTrue(manager._worker_thread.is_alive())
        self.assertEqual(backend.cuenta_por_marcador("marcador-h2"), 0,
                         "se ejecutó un job sin admisión")


# -------------------------- HIGH-5: deadline de admisión por job (§J)
class DeadlineAdmisionTests(unittest.TestCase):
    """La espera por admisión tiene fin: deadline persistido por job
    y transición a failed (admission_timeout) al agotarlo."""

    def test_33_deadline_persistido_y_agotado(self):
        temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_i2_ded_"))
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        jobs_dir = temp_dir / "jobs"
        backend = BackendFalso()
        self.addCleanup(backend.server_close)
        manager = JobsManager(
            jobs_dir=jobs_dir, backend_url=backend.url,
            dispatcher=_dispatcher_que_nunca_admite(),
            rate_limit_lookup=lambda pid: dict(RL_SATURADO))
        self.addCleanup(manager.stop)

        for proyecto in ("proyecto-alpha", "proyecto-beta"):
            with self.subTest(proyecto=proyecto):
                status, res = manager.create_job(
                    proyecto, "infer_text",
                    {"messages": [{"role": "user",
                                   "content": f"satura-{proyecto}"}]},
                    f"i2-ded-{proyecto}")
                self.assertEqual(status, 202)
                archivo = (jobs_dir / "data" / proyecto
                           / f"{res['job_id']}.json")
                job = json.loads(archivo.read_text(encoding="utf-8"))
                self.assertIn("admission_deadline", job,
                              "el deadline de admisión no se persistió")
                # Saturación sostenida: el deadline se adelanta en
                # disco (reloj del sistema, sin sleeps largos) y el
                # worker debe cerrarlo en el reintento inmediato.
                job["admission_deadline"] = "2000-01-01T00:00:00+00:00"
                archivo.write_text(json.dumps(job), encoding="utf-8")
                final = _esperar_terminal(manager, proyecto,
                                          res["job_id"], plazo=10.0)
                self.assertEqual(final["state"], "failed")
                self.assertEqual(final["error"]["code"],
                                 "admission_timeout")


# ----------------------------------- HIGH-6/D4: barrido y temporales
class BarridoPeriodicoTests(unittest.TestCase):
    """El worker barre periódicamente sin tráfico: vencidos a
    tombstone, temporales huérfanos y claims fuera; el fallo de una
    purga es observable y se reintenta."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_i2_bar_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.jobs_dir = self.temp_dir / "jobs"
        self.backend = BackendFalso()
        self.addCleanup(self.backend.server_close)

    def _manager(self, **kwargs):
        manager = JobsManager(jobs_dir=self.jobs_dir,
                              backend_url=self.backend.url, **kwargs)
        self.addCleanup(manager.stop)
        return manager

    def _forzar_expiracion(self, project_id, job_id):
        archivo = (self.jobs_dir / "data" / project_id
                   / f"{job_id}.json")
        job = json.loads(archivo.read_text(encoding="utf-8"))
        job["expires_at"] = (
            datetime.now(timezone.utc)
            - timedelta(hours=1)).isoformat()
        archivo.write_text(json.dumps(job), encoding="utf-8")
        return archivo

    def test_34_barrido_sin_trafico(self):
        manager = self._manager(intervalo_barrido_s=0.2)
        status, res = manager.create_job(
            "proyecto-alpha", "infer_text",
            {"messages": [{"role": "user", "content": "sin-trafico"}]},
            "i2-barrido")
        self.assertEqual(status, 202)
        _esperar_terminal(manager, "proyecto-alpha", res["job_id"])
        archivo = self._forzar_expiracion("proyecto-alpha", res["job_id"])
        limite = time.monotonic() + 8.0
        while time.monotonic() < limite:
            en_disco = json.loads(archivo.read_text(encoding="utf-8"))
            if en_disco.get("state") == "expired":
                break
            time.sleep(0.1)
        en_disco = json.loads(archivo.read_text(encoding="utf-8"))
        self.assertEqual(en_disco.get("state"), "expired",
                         "sin tráfico el vencido no se purgó")
        self.assertNotIn("payload", en_disco)

    def test_35_temporales_huerfanos_barridos(self):
        manager = self._manager(intervalo_barrido_s=0.2,
                                tmp_edad_s=60.0)
        dir_data = self.jobs_dir / "data" / "proyecto-alpha"
        dir_data.mkdir(parents=True, exist_ok=True)
        huerfano = dir_data / "job-x.json.tmp.111.222"
        huerfano.write_text('{"prompt": "dato-sensible-del-cliente"}',
                            encoding="utf-8")
        hace_una_hora = time.time() - 3600
        os.utime(huerfano, (hace_una_hora, hace_una_hora))
        reciente = dir_data / "job-y.json.tmp.333.444"
        reciente.write_text('{"en_curso": true}', encoding="utf-8")
        limite = time.monotonic() + 8.0
        while time.monotonic() < limite and huerfano.exists():
            time.sleep(0.1)
        self.assertFalse(huerfano.exists(),
                         "el temporal sensible huérfano sobrevivió")
        self.assertTrue(reciente.exists(),
                        "se borró un temporal de una escritura en curso")

    def test_36_claims_huerfanos_barridos(self):
        manager = self._manager(intervalo_barrido_s=0.2)
        claims = self.jobs_dir / "claims"
        claims.mkdir(parents=True, exist_ok=True)
        fantasma = claims / "job-fantasma.lock"
        fantasma.write_bytes(b"")
        # job terminal con claim abandonado: se retira
        _escribir_job_en_disco(
            self.jobs_dir, "proyecto-alpha", "job-term-1",
            {"messages": [{"role": "user", "content": "t"}]},
            clave="i2-term")
        archivo = (self.jobs_dir / "data" / "proyecto-alpha"
                   / "job-term-1.json")
        job = json.loads(archivo.read_text(encoding="utf-8"))
        job["state"] = "failed"
        archivo.write_text(json.dumps(job), encoding="utf-8")
        terminal = claims / "job-term-1.lock"
        terminal.write_bytes(b"")
        # claim sostenido por otro ejecutor (flock activo): se respeta
        sostenido = claims / "job-ajeno.lock"
        fd_ajeno = os.open(sostenido, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd_ajeno, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.addCleanup(os.close, fd_ajeno)
        limite = time.monotonic() + 8.0
        while time.monotonic() < limite and fantasma.exists():
            time.sleep(0.1)
        self.assertFalse(fantasma.exists(),
                         "el claim de un job inexistente sobrevivió")
        self.assertFalse(terminal.exists(),
                         "el claim de un job terminal sobrevivió")
        self.assertTrue(sostenido.exists(),
                        "se retiró el claim de un ejecutor vivo")

    def test_37_purga_fallida_observable_y_reintenta(self):
        manager = self._manager(intervalo_barrido_s=999.0)
        status, res = manager.create_job(
            "proyecto-alpha", "infer_text",
            {"messages": [{"role": "user", "content": "dato-privado"}]},
            "i2-purga-falla")
        self.assertEqual(status, 202)
        _esperar_terminal(manager, "proyecto-alpha", res["job_id"])
        archivo = self._forzar_expiracion("proyecto-alpha", res["job_id"])
        real = manager._purgar_job
        estado = {"n": 0}

        def purga_que_falla_una_vez(job):
            estado["n"] += 1
            if estado["n"] == 1:
                raise OSError("disfo lleno")
            return real(job)

        with mock.patch.object(manager, "_purgar_job",
                               purga_que_falla_una_vez):
            status1, _ = manager.get_job("proyecto-alpha",
                                         res["job_id"])
        self.assertEqual(status1, 410)
        en_disco = json.loads(archivo.read_text(encoding="utf-8"))
        self.assertNotEqual(en_disco.get("state"), "expired",
                            "get_job presentó como lograda una purga "
                            "que falló")
        self.assertGreaterEqual(
            getattr(manager, "fallos_purga", -1), 1,
            "el fallo de purga no quedó registrado de forma observable")
        status2, _ = manager.get_job("proyecto-alpha", res["job_id"])
        self.assertEqual(status2, 410)
        en_disco = json.loads(archivo.read_text(encoding="utf-8"))
        self.assertEqual(en_disco.get("state"), "expired",
                         "la purga no reintentó tras el fallo")


# --------------------- regresiones de la ronda adversarial (intento 2)
class RegresionesRondaAdversarialTests(unittest.TestCase):
    """Hallazgos del revisor de contexto fresco: el 202 nunca puede
    apoyarse en un registro ya borrado (doble ejecución); el deadline
    vencido durante la espera no ejecuta; el barrido cuenta sus
    fallos de purga."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_i2_adv_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.jobs_dir = self.temp_dir / "jobs"
        self.backend = BackendFalso()
        self.addCleanup(self.backend.server_close)
        self.payload = {"messages": [{"role": "user", "content": "adv"}]}

    def _manager(self, **kwargs):
        manager = JobsManager(jobs_dir=self.jobs_dir,
                              backend_url=self.backend.url, **kwargs)
        self.addCleanup(manager.stop)
        return manager

    @staticmethod
    def _fsync_que_falla_en(real, indices):
        estado = {"n": 0}
        cerrojo = threading.Lock()

        def envoltura(fd):
            with cerrojo:
                estado["n"] += 1
                n = estado["n"]
            if n in indices:
                raise OSError(f"fallo inyectado en fsync {n}")
            return real(fd)

        return envoltura

    def test_40_fsync_sostenido_no_duplica_ejecucion(self):
        # El BLOCKER de la ronda: fsync fallando tras el link Y tras
        # el unlink del registro no puede acabar en un 202 sin
        # registro (reintento con la misma clave ejecutando dos vez).
        manager = self._manager()
        with mock.patch(
                "os.fsync",
                self._fsync_que_falla_en(os.fsync, {4, 5})):
            status1, _ = manager.create_job(
                "proyecto-alpha", "infer_text", self.payload, "i2-adv40")
        self.assertEqual(status1, 500,
                         "202 apoyado en un registro no constante")
        status2, res2 = manager.create_job(
            "proyecto-alpha", "infer_text", self.payload, "i2-adv40")
        self.assertEqual(status2, 202)
        data = [p for p in (self.jobs_dir / "data").rglob("*.json")]
        registros = [p for p in (self.jobs_dir / "idempotency")
                     .rglob("*.json")]
        self.assertEqual(len(data), 1,
                         "más de un job vivo para una misma clave")
        self.assertEqual(len(registros), 1,
                         "el registro de la clave no quedó único")
        final = _esperar_terminal(manager, "proyecto-alpha",
                                  res2["job_id"])
        self.assertEqual(final["state"], "succeeded")

    def test_41_deadline_vencido_durante_la_espera(self):
        # dispatcher que concede tarde: el deadline vence durante la
        # espera de acquire; el job no se ejecuta tarde.
        class DispatcherLento:
            def __init__(self):
                self.concesiones = 0

            def acquire_slot(self, project_id, rl_config, timeout=None):
                time.sleep(1.0)
                self.concesiones += 1

            def release_slot(self, project_id):
                pass

        _escribir_job_en_disco(
            self.jobs_dir, "proyecto-alpha", "job-tarde-1",
            {"messages": [{"role": "user", "content": "marcador-tarde"}]},
            clave="i2-tarde")
        archivo = (self.jobs_dir / "data" / "proyecto-alpha"
                   / "job-tarde-1.json")
        job = json.loads(archivo.read_text(encoding="utf-8"))
        job["admission_deadline"] = (
            datetime.now(timezone.utc)
            + timedelta(seconds=0.6)).isoformat()
        archivo.write_text(json.dumps(job), encoding="utf-8")
        lento = DispatcherLento()
        manager = self._manager(dispatcher=lento,
                                rate_limit_lookup=lambda pid: {})
        final = _esperar_terminal(manager, "proyecto-alpha",
                                  "job-tarde-1", plazo=15.0)
        self.assertEqual(final["state"], "failed",
                         f"se ejecutó con el deadline vencido: {final}")
        self.assertEqual(final["error"]["code"], "admission_timeout")
        self.assertEqual(
            self.backend.cuenta_por_marcador("marcador-tarde"), 0,
            "el backend recibió el job vencido")
        self.assertGreaterEqual(lento.concesiones, 1,
                                "el re-chequeo no cubrió la espera")

    def test_42_barrido_cuenta_fallos_de_purga(self):
        manager = self._manager(intervalo_barrido_s=0.2)
        status, res = manager.create_job(
            "proyecto-alpha", "infer_text",
            {"messages": [{"role": "user", "content": "barr-falla"}]},
            "i2-adv42")
        self.assertEqual(status, 202)
        _esperar_terminal(manager, "proyecto-alpha", res["job_id"])
        archivo = (self.jobs_dir / "data" / "proyecto-alpha"
                   / f"{res['job_id']}.json")
        job = json.loads(archivo.read_text(encoding="utf-8"))
        job["expires_at"] = (
            datetime.now(timezone.utc)
            - timedelta(hours=1)).isoformat()
        archivo.write_text(json.dumps(job), encoding="utf-8")
        with mock.patch.object(
                JobsManager, "_purgar_job",
                side_effect=OSError("disfo lleno")):
            limite = time.monotonic() + 8.0
            while time.monotonic() < limite \
                    and manager.fallos_purga < 1:
                time.sleep(0.1)
        self.assertGreaterEqual(
            manager.fallos_purga, 1,
            "el barrido silenció los fallos de purga")
        en_disco = json.loads(archivo.read_text(encoding="utf-8"))
        self.assertNotEqual(en_disco.get("state"), "expired")


    def test_43_cierre_por_defecto_desde_running(self):
        # rama running de _cerrar_por_defecto (ronda adversarial): el
        # defecto no-ErrorV2 no deja colgado un job en ejecución.
        manager = self._manager()  # arranque con el dir limpio
        _escribir_job_en_disco(
            self.jobs_dir, "proyecto-alpha", "job-running-x",
            self.payload, clave="i2-running-x")
        archivo = (self.jobs_dir / "data" / "proyecto-alpha"
                   / "job-running-x.json")
        job = json.loads(archivo.read_text(encoding="utf-8"))
        job["state"] = "running"
        archivo.write_text(json.dumps(job), encoding="utf-8")
        manager._cerrar_por_defecto(
            "proyecto-alpha", "job-running-x",
            RuntimeError("release_slot hostil"))
        final = _esperar_terminal(manager, "proyecto-alpha",
                                  "job-running-x", plazo=5.0)
        self.assertEqual(final["state"], "failed")
        self.assertEqual(final["error"]["code"], "worker_internal_error")


# --------------------------- MED-8/MED-9: frontera controlada y aislada
class FronteraIntento2Tests(unittest.TestCase):
    """operation no cadena responde 400; build_server sin jobs_dir no
    toca run/jobs ni construye JobsManager (501 hasta asignación)."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="lfm3_i2_frt_"))
        cls.tokens_path = cls.temp_dir / "tokens.json"
        config = {
            "version": 1,
            "projects": {
                "proyecto-alpha": {
                    "token_sha256": hashlib.sha256(
                        TOKEN_ALPHA.encode()).hexdigest(),
                    "revoked": False,
                    "scopes": ["jobs:create", "jobs:read", "jobs:cancel",
                               "infer:text"],
                    "rate_limit": {"requests_per_minute": 600,
                                   "burst": 50, "max_queue": 10,
                                   "queue_timeout_seconds": 5.0},
                },
            },
        }
        cls.tokens_path.write_text(json.dumps(config), encoding="utf-8")
        cls.backend = BackendFalso()
        # jobs_dir inyectado (MED-9): si la firma aún no lo admite,
        # se construye como hoy y se sustituye el manager (el test
        # seguirá fallando por su razón, no por la firma).
        try:
            cls.server = build_server(
                ("127.0.0.1", 0),
                backend=cls.backend.url,
                auth_enabled=True,
                tokens_registry=TokenRegistry(cls.tokens_path),
                dispatcher=FairQueueDispatcher(),
                jobs_dir=cls.temp_dir / "jobs",
            )
        except TypeError:
            cls.server = build_server(
                ("127.0.0.1", 0),
                backend=cls.backend.url,
                auth_enabled=True,
                tokens_registry=TokenRegistry(cls.tokens_path),
                dispatcher=FairQueueDispatcher(),
            )
            cls.server.jobs_manager.stop()
            cls.server.jobs_manager = JobsManager(
                jobs_dir=cls.temp_dir / "jobs",
                backend_url=cls.backend.url)
        cls.puerto = cls.server.server_address[1]
        cls.hilo = threading.Thread(target=cls.server.serve_forever,
                                    daemon=True)
        cls.hilo.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.jobs_manager.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.backend.server_close()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def _post_crudo(self, cuerpo: bytes) -> tuple[int, dict]:
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.puerto}/jobs",
            data=cuerpo,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {TOKEN_ALPHA}",
                "X-Project-ID": "proyecto-alpha",
                "Idempotency-Key": f"i2-{uuid.uuid4().hex[:12]}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())

    def test_38_operation_no_cadena_400_controlado(self):
        for op_mala in (["infer_text"], 42, {"op": "infer_text"}, None):
            cuerpo = json.dumps({
                "operation": op_mala,
                "payload": {"messages": [
                    {"role": "user", "content": "x"}]},
            }).encode("utf-8")
            status, res = self._post_crudo(cuerpo)
            self.assertEqual(status, 400,
                             f"operation {op_mala!r}: {status} {res}")
            self.assertEqual(res["error"]["code"],
                             "unsupported_operation")

    def test_39_build_server_sin_jobs_dir_no_toca_run(self):
        cwd_original = Path.cwd()
        clon = Path(tempfile.mkdtemp(prefix="lfm3_i2_clon_"))
        self.addCleanup(shutil.rmtree, clon, ignore_errors=True)
        os.chdir(clon)
        self.addCleanup(os.chdir, cwd_original)
        servidor = build_server(("127.0.0.1", 0),
                                backend=self.backend.url,
                                auth_enabled=False)
        hilo_servidor = threading.Thread(target=servidor.serve_forever,
                                         daemon=True)
        hilo_servidor.start()
        try:
            self.assertIsNone(
                getattr(servidor, "jobs_manager", None),
                "build_server construyó un JobsManager sin jobs_dir")
            puerto = servidor.server_address[1]
            req = urllib.request.Request(
                f"http://127.0.0.1:{puerto}/jobs/job-cualquiera")
            try:
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    status = resp.status
                    cuerpo = json.loads(resp.read().decode())
            except urllib.error.HTTPError as exc:
                status = exc.code
                cuerpo = json.loads(exc.read().decode())
            self.assertEqual(status, 501, f"{status} {cuerpo}")
            self.assertEqual(cuerpo["error"]["code"],
                             "not_implemented")
        finally:
            servidor.shutdown()
            servidor.server_close()
        self.assertFalse(
            (clon / "run" / "jobs").exists(),
            "build_server creó run/jobs en un clon nuevo")


if __name__ == "__main__":
    unittest.main()
