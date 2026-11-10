#!/usr/bin/env python3
"""Manejador de Trabajos Largos en Segundo Plano (Perfil J) — Fase I5.

Contrato: docs/contracts/perfiles-servicio-v2.md (§J)
Especificación: docs/specs/SPEC-i5-jobs.md
Decisión: docs/adr/ADR-012-trabajos-largos-persistencia-idempotencia.md
Expedientes: docs/reviews/evidence/fix-i5-jobs-frontera/ (fix-i5) y
docs/reviews/evidence/fix-i5-despacho/ (RESIDUAL-MED, LOW-1, LOW-7).

Garantías: idempotencia canónica RFC 8785 con tombstone 24 h (§J);
persistencia atómica durable en jobs_storage (el registro de
idempotencia es el commit de la admisión, recuperable ante fallos
posteriores al link); una sola instancia por jobs_dir con cerrojo
flock (D1) que además sostiene el barrido periódico de vencidos,
temporales huérfanos y claims (D4); recuperación fail-closed;
admisión compartida con H/M con deadline por job (§J: la espera
tiene fin); salida del modelo validada (completitud y esquema) antes
de persistir; retención §J con purga verificable y permisos
0600/0700. El cifrado en reposo queda como desviación declarada y
requisito bloqueante para exponer /jobs (D3).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import sys
import threading
import urllib.error
import urllib.request
from typing import Any, Callable

from gateway_core import ErrorV2, _error, validar_salida

# La serialización canónica vive en canonical_json y la persistencia
# durable en jobs_storage (reorganización del expediente, §3.3 del
# estándar: mover sin cambiar comportamiento). El serializador se
# re-exporta porque la frontera pública del módulo lo prometía.
from canonical_json import canonical_json_rfc8785
# La recuperación al arranque y el barrido de vencidos (purga) viven
# en jobs_recovery como mixin (reorganización pura del intento 4,
# §3.3 del estándar: mismos métodos, mismo comportamiento).
from jobs_recovery import JobsRecoveryMixin
from jobs_storage import (
    CommitTrasLinkError, JobsDirOcupado, JobsStorage,
)

# JobsDirOcupado vive en jobs_storage (es E/S del árbol run/jobs);
# se re-exporta porque la frontera pública de este módulo la prometía.
__all__ = ["JobsDirOcupado", "JobsManager", "canonical_json_rfc8785"]

IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9_\-\.:]{1,64}$")
ALLOWED_OPERATIONS = {"infer_text", "infer_vision", "infer_audio", "infer_video"}
DEFAULT_TTL_SECONDS = 3600  # 1 hora tras terminal (§J)
MAX_TTL_SECONDS = 86400  # 24 horas
MAX_QUEUED_PER_PROJECT = 1
MAX_QUEUED_GLOBAL = 8
ADMISION_TIMEOUT_S = 60.0  # presupuesto de cola compartido (§J)
REINTENTO_ADMISION_S = 0.5
ESPERA_ADMISION_S = 60.0  # deadline total de admisión por job (§J)
INTERVALO_BARRIDO_S = 30.0  # barrido periódico dentro del worker (D4)
TMP_EDAD_S = 300.0  # un tmp legítimo vive milisegundos (D4)
MSG_IDEMPOTENCY_CONFLICT = (
    "Idempotency-Key ya utilizada con un cuerpo de solicitud diferente")


def _respuesta_error(status: int, code: str, message: str) -> tuple[int, dict]:
    """Cuerpo de error homogéneo (la frontera HTTP lo reenvía)."""
    return status, {"error": {"code": code, "message": message}}


def _ahora_utc() -> datetime:
    """Reloj de pared real (UTC): defecto del reloj inyectable (LOW-7)."""
    return datetime.now(timezone.utc)


class JobsManager(JobsRecoveryMixin):
    """Gestor de ciclo de vida, persistencia y ejecución de trabajos largos."""

    def __init__(self, jobs_dir: str | Path | None = None,
                 backend_url: str = "http://127.0.0.1:8091",
                 dispatcher: Any = None,
                 rate_limit_lookup: Callable[[str], dict] | None = None,
                 intervalo_barrido_s: float = INTERVALO_BARRIDO_S,
                 tmp_edad_s: float = TMP_EDAD_S,
                 reloj: Callable[[], datetime] | None = None):
        if jobs_dir:
            base_dir = Path(jobs_dir)
        else:
            base_dir = Path(os.environ.get("LFM3_JOBS_DIR", "run/jobs"))
        self.storage = JobsStorage(base_dir)
        self.data_dir = self.storage.data_dir
        self.idemp_dir = self.storage.idemp_dir
        self.claims_dir = self.storage.claims_dir
        # D1: una sola instancia por jobs_dir. El cerrojo se toma
        # ANTES de cualquier recuperación: una segunda instancia
        # falla cerrada sin worker ni startup_recover. Si el arranque
        # posterior falla, el cerrojo se libera (ronda adversarial:
        # un fd huérfano bloquearía el jobs_dir para siempre).
        self._fd_instancia = self.storage.tomar_cerrojo_instancia()
        try:
            self._arrancar(backend_url, dispatcher, rate_limit_lookup,
                           intervalo_barrido_s, tmp_edad_s, reloj)
        except BaseException:
            os.close(self._fd_instancia)
            self._fd_instancia = None
            raise

    def _arrancar(self, backend_url: str, dispatcher: Any,
                  rate_limit_lookup: Callable[[str], dict] | None,
                  intervalo_barrido_s: float, tmp_edad_s: float,
                  reloj: Callable[[], datetime] | None) -> None:
        """Resto del arranque; se ejecuta con el cerrojo tomado."""
        # LOW-7: reloj inyectable (pared UTC); barrido, purga y
        # deadlines dependen de él; tests de tiempo con reloj falso.
        self.reloj = reloj if reloj is not None else _ahora_utc
        self.backend_url = backend_url.rstrip("/")
        # Admisión compartida con H/M (HIGH-1); None = sin (tests).
        self.dispatcher = dispatcher
        self.rate_limit_lookup = rate_limit_lookup
        self.lock = threading.Lock()
        self.work_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.running_job_id: str | None = None
        # [HIGH ronda 3] Jobs puestos en la cola del worker: evita el
        # doble encolado al reconciliar reintentos; se descarta al
        # cerrar o purgar (ver _asegurar_despacho).
        self._en_cola: set[str] = set()
        self._stop_event = threading.Event()
        # D4: barrido periódico dentro del bucle del worker; el fallo
        # de una purga queda contado y visible (HIGH-6).
        self.intervalo_barrido_s = intervalo_barrido_s
        self.tmp_edad_s = tmp_edad_s
        self.fallos_purga = 0
        self._ultimo_barrido = self.reloj()
        self.startup_recover()
        self._worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="jobs-worker")
        self._worker_thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Detiene el worker y libera el jobs_dir (D1). El fd de
        instancia sólo se cierra si el hilo terminó de verdad; vivo
        tras el plazo, el directorio queda tomado (fail-closed, MED-3
        ronda 2) con constancia en stderr; se puede volver a llamar
        cuando el worker haya terminado."""
        self._stop_event.set()
        self.work_queue.put(("", ""))  # Despertar thread
        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)
        if self._worker_thread.is_alive():
            print(f"jobs: worker vivo tras stop(timeout={timeout}s); "
                  f"no se libera el cerrojo de "
                  f"{self.storage.base_dir} (fail-closed, D1)",
                  file=sys.stderr, flush=True)
            return
        if self._fd_instancia is not None:
            os.close(self._fd_instancia)
            self._fd_instancia = None

    def _save_job_atomically(self, job_dict: dict) -> None:
        """Delega la escritura durable en el almacenamiento; los fallos
        de E/S se propagan (BLOCKER-2: nada se reporta sin que conste)."""
        self.storage.save_job(job_dict)

    def _load_job(self, project_id: str, job_id: str) -> dict | None:
        return self.storage.load_job(project_id, job_id)

    def _registro_confirma_admision(self, job: dict) -> bool:
        """True si el registro de idempotencia apunta a este job vivo."""
        clave = job.get("idempotency_key")
        if not isinstance(clave, str):
            return False
        rec = self.storage.lookup_idempotency_record(
            job.get("project_id", ""), clave)
        return bool(rec and rec.get("job_id") == job.get("job_id"))

    def _descartar_job_sin_admision(self, project_id: str, job_id: str):
        self.storage.eliminar_job(project_id, job_id)

    def _asegurar_despacho(self, job: dict) -> bool:
        """[HIGH, ronda 3] Reconciliación del reintento: un job
        `queued` cuyo despacho no consta (doble fallo de retiro tras
        CommitTrasLinkError) se encola UNA sola vez; si ya consta en
        cola, no se toca (sin doble encolado ni doble ejecución).
        False = despacho no comprobable: arriba responde fallo
        explícito, jamás un 202 sin avance."""
        job_id = job.get("job_id")
        proyecto = job.get("project_id")
        if job.get("state") != "queued":
            return True  # en ejecución o terminal: nada que despachar
        if not isinstance(job_id, str) or not isinstance(proyecto, str):
            return False  # ilegible: no comprobable
        if job_id not in self._en_cola:
            self.work_queue.put((proyecto, job_id))
            self._en_cola.add(job_id)
        return True

    def _reconciliar_abandono(self, project_id: str, job_id: str) -> None:
        """RESIDUAL-MED (seguimiento fix-i5-despacho): un job retirado
        de la cola y abandonado sin running persistido queda queued en
        disco, fuera de la cola y dentro de _en_cola; el reintento
        respondería 202 sin avance. Relectura bajo el lock: si sigue
        queued, sale de _en_cola y el reintento lo reencola vía
        _asegurar_despacho. Relectura ilegible: fail-closed (punto 3)."""
        with self.lock:
            job = self._load_job(project_id, job_id)
            if job is not None and job.get("state") == "queued":
                self._en_cola.discard(job_id)

    def create_job(self, project_id: str, operation: str, payload: dict,
                   idempotency_key: str,
                   ttl_seconds: int = DEFAULT_TTL_SECONDS
                   ) -> tuple[int, dict]:
        """Crea o recupera un trabajo con commit durable de admisión."""
        if not isinstance(idempotency_key, str) \
                or not IDEMPOTENCY_KEY_RE.match(idempotency_key):
            return _respuesta_error(
                400, "invalid_idempotency_key",
                "Idempotency-Key debe ser ASCII de 1 a 64 caracteres "
                "válidos")
        if not isinstance(operation, str) \
                or operation not in ALLOWED_OPERATIONS:
            return _respuesta_error(
                400, "unsupported_operation",
                f"Operación '{operation}' no admitida en Perfil J")
        if not isinstance(payload, dict):
            return _respuesta_error(
                400, "invalid_payload", "payload debe ser un objeto JSON")
        try:
            canon = canonical_json_rfc8785(
                {"operation": operation, "payload": payload})
            payload_hash = hashlib.sha256(canon).hexdigest()
        except Exception as exc:
            return _respuesta_error(
                400, "canonicalization_error",
                f"Error canonicalizando payload: {exc}")

        self._purgar_expirados()
        with self.lock:
            rec = self.storage.lookup_idempotency_record(
                project_id, idempotency_key)
            if rec:
                if rec["payload_hash"] != payload_hash:
                    return _respuesta_error(
                        409, "idempotency_conflict",
                        MSG_IDEMPOTENCY_CONFLICT)
                existente = self._load_job(project_id, rec["job_id"])
                if existente is None:
                    # Registro huérfano (crash entre link y
                    # reconciliación): retirarlo y readmitir; la clave
                    # no queda bloqueada (BLOCKER-1). Si ni siquiera
                    # se puede retirar, fail-closed explícito.
                    if not self.storage.retirar_registro(
                            project_id, idempotency_key):
                        return _respuesta_error(
                            500, "storage_error",
                            "Registro de idempotencia huérfano "
                            "irretirable; admisión denegada")
                elif existente.get("state") == "expired" \
                        or self._vencido(existente):
                    # Registro vivo con resultado caducado: dentro del
                    # tombstone nunca se re-infiera (§J).
                    return _respuesta_error(
                        410, "job_expired",
                        "El trabajo asociado a esta clave ya expiró; "
                        "use una clave nueva")
                else:
                    # [HIGH ronda 3] El 202 de reintento debe avanzar:
                    # si el job sigue queued y su despacho no consta,
                    # encolarlo UNA sola vez; si no se puede comprobar,
                    # fallo explícito, nunca un 202 sin avance.
                    if not self._asegurar_despacho(existente):
                        return _respuesta_error(
                            500, "storage_error",
                            "Job existente ilegible; no se puede "
                            "comprobar su despacho (reintente)")
                    return 202, self._vista_admision(existente)

            queued_proj, queued_global = self._contar_encolados(project_id)
            if queued_proj >= MAX_QUEUED_PER_PROJECT:
                return _respuesta_error(
                    429, "queue_limit_per_project_exceeded",
                    f"El proyecto ya tiene {queued_proj} trabajo(s) en "
                    f"cola (máximo {MAX_QUEUED_PER_PROJECT})")
            if queued_global >= MAX_QUEUED_GLOBAL:
                return _respuesta_error(
                    429, "global_queue_limit_exceeded",
                    f"Cola global de trabajos saturada ({queued_global} "
                    f"en espera)")

            # Job durable primero, registro después: el registro es
            # el commit (link exclusivo); sin él no hay 202 (BLOCKER-2).
            ahora = self.reloj()
            ttl = ttl_seconds if isinstance(ttl_seconds, int) \
                and not isinstance(ttl_seconds, bool) else DEFAULT_TTL_SECONDS
            ttl = min(max(ttl, 60), MAX_TTL_SECONDS)
            expira = ahora + timedelta(seconds=ttl)
            # HIGH-5: la espera por admisión tiene fin; el deadline
            # viaja con el job (persistido) y su agotamiento cierra
            # el job en failed (admission_timeout).
            deadline_admision = ahora + timedelta(seconds=ESPERA_ADMISION_S)
            job_id = "job-" + hashlib.sha256(
                f"{project_id}:{idempotency_key}:{ahora.isoformat()}"
                .encode()).hexdigest()[:16]
            job_dict = {
                "job_id": job_id,
                "contract_version": "2",
                "project_id": project_id,
                "operation": operation,
                "payload": payload,
                "idempotency_key": idempotency_key,
                "ttl_seconds": ttl,
                "state": "queued",
                "created_at": ahora.isoformat(),
                "started_at": None,
                "completed_at": None,
                "expires_at": expira.isoformat(),
                "admission_deadline": deadline_admision.isoformat(),
                "result": None,
                "error": None,
                "model_revision": "LiquidAI/LFM3-Omni-2B-GGUF",
            }
            try:
                self._save_job_atomically(job_dict)
            except OSError:
                # Sin registro no hay admisión: retirar el job también
                # aquí (el fallo puede ser posterior al replace) o el
                # huérfano queued bloquearía el reintento con 429
                # (BLOCKER-1). Si el retiro falla, el arranque
                # reconcilia (admission_unconfirmed).
                self._descartar_job_sin_admision(project_id, job_id)
                return _respuesta_error(
                    500, "storage_error",
                    "No se pudo persistir el trabajo; admisión denegada")
            try:
                self.storage.commit_registro_idempotencia(
                    project_id, idempotency_key, job_id, payload_hash)
            except FileExistsError:
                return self._resolver_rival(
                    project_id, idempotency_key, payload_hash, job_id)
            except CommitTrasLinkError:
                # BLOCKER-1 + LOW-5 (ronda 2): el registro quedó
                # enlazado con durabilidad incierta y la admisión sólo
                # constaría con fsync (§J: persistir… atómicamente).
                # Nunca 202 sobre esa pareja: 500 fail-closed. El job
                # se descarta siempre; el registro se retira si el
                # disco lo permite (reintento limpio) y si no, el
                # reintento reconcilia por la vía del huérfano. El
                # retorno de retirar no decide aquí: el reintento
                # lee el disco, no esta respuesta.
                self.storage.retirar_registro(
                    project_id, idempotency_key)
                self._descartar_job_sin_admision(project_id, job_id)
                return _respuesta_error(
                    500, "storage_error",
                    "Registro de idempotencia sin confirmación "
                    "durable; admisión denegada (reintente)")
            except OSError:
                self._descartar_job_sin_admision(project_id, job_id)
                return _respuesta_error(
                    500, "storage_error",
                    "No se pudo persistir el registro de idempotencia; "
                    "admisión denegada")
            self.work_queue.put((project_id, job_id))
            self._en_cola.add(job_id)
            return 202, self._vista_admision(job_dict)

    def _resolver_rival(self, project_id: str, idempotency_key: str,
                        payload_hash: str, job_id_propio: str):
        """Otra instancia commitó la misma clave: seguir SU admisión."""
        self._descartar_job_sin_admision(project_id, job_id_propio)
        rival = self.storage.lookup_idempotency_record(
            project_id, idempotency_key)
        if rival is None:
            return _respuesta_error(
                500, "storage_error",
                "Registro de idempotencia ilegible tras conflicto de commit")
        if rival["payload_hash"] != payload_hash:
            return _respuesta_error(
                409, "idempotency_conflict", MSG_IDEMPOTENCY_CONFLICT)
        existente = self._load_job(project_id, rival["job_id"])
        if existente is None:
            return _respuesta_error(
                500, "storage_error", "Job de la admisión rival ilegible")
        if existente.get("state") == "expired" or self._vencido(existente):
            return _respuesta_error(
                410, "job_expired",
                "El trabajo asociado a esta clave ya expiró; use una "
                "clave nueva")
        # LOW-1 (ronda 4): el 202 del rival pasa por la reconciliación
        # del despacho; bajo D1 es rama defensiva, jamás 202 sin avance.
        if not self._asegurar_despacho(existente):
            return _respuesta_error(
                500, "storage_error",
                "Job de la admisión rival ilegible; no se puede "
                "comprobar su despacho (reintente)")
        return 202, self._vista_admision(existente)

    @staticmethod
    def _vista_admision(job: dict) -> dict:
        """Respuesta 202 de admisión (SPEC-i5 §2.1)."""
        return {
            "job_id": job["job_id"], "state": job["state"],
            "status_url": f"/jobs/{job['job_id']}",
            "created_at": job["created_at"], "expires_at": job["expires_at"]}

    def _contar_encolados(self, project_id: str) -> tuple[int, int]:
        """(queued del proyecto, queued globales) según disco. Contar
        sólo `queued` es el contrato literal de SPEC-i5 §2.1 (D2); con
        una instancia por jobs_dir (D1) y contar+commit bajo
        self.lock, el conteo no tiene carrera con el worker."""
        queued_proj = 0
        queued_global = 0
        for p_dir in self.data_dir.iterdir():
            if not p_dir.is_dir():
                continue
            for f_job in p_dir.glob("*.json"):
                try:
                    j_data = json.loads(f_job.read_text(encoding="utf-8"))
                    if j_data.get("state") == "queued":
                        queued_global += 1
                        if j_data.get("project_id") == project_id:
                            queued_proj += 1
                except Exception:
                    pass
        return queued_proj, queued_global

    def get_job(self, project_id: str, job_id: str) -> tuple[int, dict]:
        """Consulta aislada por proyecto (ajeno: 404 fail-closed)."""
        job = self._load_job(project_id, job_id)
        if not job or job.get("project_id") != project_id:
            return _respuesta_error(404, "not_found",
                                    "Trabajo no encontrado")
        if self._vencido(job):
            # Purga verificable al expirar (HIGH-2): sale del disco.
            # Si la purga falla, el 410 sigue siendo cierto (el
            # resultado no se entrega tras el TTL) pero el fallo
            # queda contado y visible; el barrido reintenta (HIGH-6).
            # LOW-6 (ronda 2): bajo self.lock, para que el tombstone
            # no se intercale con la transición running del worker.
            # [MED ronda 3] El snapshot de arriba pudo quedar viejo:
            # recargar estado y vencimiento BAJO el lock justo antes
            # de purgar; un running jamás se purga con estado viejo.
            if job.get("state") not in ("running", "expired"):
                try:
                    with self.lock:
                        actual = self._load_job(project_id, job_id)
                        if actual is not None \
                                and actual.get("state") not in (
                                    "running", "expired") \
                                and self._vencido(actual):
                            self._purgar_job(actual)
                except OSError as exc:
                    self.fallos_purga += 1
                    print(f"jobs: purga fallida de {job.get('job_id')}: "
                          f"{exc!r}", file=sys.stderr, flush=True)
            return _respuesta_error(
                410, "job_expired",
                "El resultado del trabajo ha expirado (TTL vencido)")
        return 200, {
            "job_id": job.get("job_id"),
            "contract_version": job.get("contract_version", "2"),
            "project_id": job.get("project_id"),
            "operation": job.get("operation"), "state": job.get("state"),
            "created_at": job.get("created_at"),
            "started_at": job.get("started_at"),
            "completed_at": job.get("completed_at"),
            "expires_at": job.get("expires_at"),
            "result": job.get("result"), "error": job.get("error"),
            "model_revision": job.get("model_revision"),
        }

    def cancel_job(self, project_id: str, job_id: str) -> tuple[int, dict]:
        """Solicita la cancelación de un trabajo propio."""
        with self.lock:
            job = self._load_job(project_id, job_id)
            if not job or job.get("project_id") != project_id:
                return _respuesta_error(404, "not_found",
                                        "Trabajo no encontrado")
            state = job.get("state")
            if state in ("succeeded", "failed", "cancelled", "expired"):
                return 200, {"job_id": job_id,
                             "cancellation_status": "already_terminal",
                             "target_state": state}
            if state == "queued":
                job["state"] = "cancelled"
                try:
                    self._cerrar(job, "cancelled")
                except OSError:
                    return _respuesta_error(
                        500, "storage_error",
                        "No se pudo persistir la cancelación")
                return 200, {"job_id": job_id,
                             "cancellation_status": "accepted",
                             "target_state": "cancelled"}
            if state == "running":
                job["state"] = "cancellation_pending"
                try:
                    self._save_job_atomically(job)
                except OSError:
                    return _respuesta_error(
                        500, "storage_error",
                        "No se pudo persistir la cancelación")
                return 200, {"job_id": job_id,
                             "cancellation_status": "pending",
                             "target_state": "cancellation_pending"}
            return 200, {"job_id": job_id,
                         "cancellation_status": "pending",
                         "target_state": state}

    def _reclamar(self, project_id: str, job_id: str) -> int | None:
        """Reclamo atómico entre procesos (HIGH-1): flock exclusivo
        por job; fd o None si lo tiene otro, no está en cola o venció.
        Un OSError real del claim se PROPAGA (RESIDUAL-MED): el worker
        reconcilia; sólo la contención del flock es None."""
        claims_dir = self.storage.asegurar_claims_dir()
        fd = os.open(claims_dir / f"{job_id}.lock",
                     os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                return None
            raise
        with self.lock:
            job = self._load_job(project_id, job_id)
            if not job or job.get("state") != "queued" or self._vencido(job):
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
                return None
        return fd

    def _soltar_reclamo(self, fd: int):
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def _admitir(self, project_id: str) -> bool:
        """Admisión compartida con H/M vía el dispatcher (HIGH-1)."""
        if self.dispatcher is None:
            return True
        limites = {}
        if self.rate_limit_lookup is not None:
            limites = self.rate_limit_lookup(project_id) or {}
        try:
            self.dispatcher.acquire_slot(
                project_id, limites, timeout=ADMISION_TIMEOUT_S)
        except ErrorV2:
            return False
        return True

    def _liberar_admision(self, project_id: str):
        if self.dispatcher is not None:
            self.dispatcher.release_slot(project_id)

    def _marcar_running(self, project_id: str, job_id: str) -> bool:
        """Pasa a running si sigue queued (la cancelación gana la
        ventana). El TTL se revalida bajo el lock: un vencido sólo
        llega aquí con el reclamo tomado ANTES de vencer (_reclamar
        rechaza los ya vencidos), así que la ejecución procede con
        constancia y el cierre nunca entrega tras el TTL (§J). Job
        ilegible: se salta sin romper el worker."""
        with self.lock:
            try:
                job = self._load_job(project_id, job_id)
                if not job or job.get("state") != "queued":
                    return False
                if self._vencido(job):
                    # [MED ronda 3] Ya estaba reclamado antes de
                    # vencer: se ejecuta, sin entregar tras el TTL.
                    print(f"jobs: {job_id} venció ya reclamado; se "
                          f"ejecuta sin entregar tras el TTL (§J)",
                          file=sys.stderr, flush=True)
                job["state"] = "running"
                job["started_at"] = self.reloj().isoformat()
                self.running_job_id = job_id
                self._save_job_atomically(job)
            except (KeyError, TypeError):
                return False
        return True

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                proj_id, job_id = self.work_queue.get(timeout=1.0)
            except queue.Empty:
                self._barrido_si_toca()
                continue
            if not proj_id or not job_id:
                continue
            try:
                fd_reclamo = self._reclamar(proj_id, job_id)
            except OSError:
                # RESIDUAL-MED: el claim falló con el job fuera de la
                # cola; reconciliar para que el reintento lo reencole.
                self._reconciliar_abandono(proj_id, job_id)
                continue
            if fd_reclamo is None:
                continue
            try:
                if self._deadline_admision_vencido(proj_id, job_id):
                    # HIGH-5: la espera por admisión tiene fin.
                    continue
                if not self._admitir(proj_id):
                    # Sin presupuesto: vuelve a la cola y se reintenta
                    # tras una pausa; nunca se ejecuta sin admisión.
                    self.work_queue.put((proj_id, job_id))
                    self._stop_event.wait(REINTENTO_ADMISION_S)
                    continue
                if self._deadline_admision_vencido(proj_id, job_id):
                    # El deadline venció DURANTE la espera de admisión
                    # (ronda adversarial): liberar el slot concedido
                    # y no ejecutar tarde.
                    self._liberar_admision(proj_id)
                    continue
                try:
                    if self._marcar_running(proj_id, job_id):
                        self._execute_single_job(proj_id, job_id)
                finally:
                    self._liberar_admision(proj_id)
            except OSError:
                # Persistencia fallida: el disco manda (fail-closed).
                # RESIDUAL-MED: si el job quedó queued sin running,
                # sacarlo de _en_cola; el reintento lo reencola.
                self._reconciliar_abandono(proj_id, job_id)
                continue
            except Exception as exc:
                # Defecto inesperado (dispatcher mal cableado): el
                # worker sobrevive y el job no queda admitido sin
                # cierre — transición durable a failed con motivo
                # (HIGH-4); el arranque reconcilia si el disco falla.
                print(f"jobs-worker: fallo inesperado en {job_id}: {exc!r}",
                      file=sys.stderr, flush=True)
                self._cerrar_por_defecto(proj_id, job_id, exc)
                continue
            finally:
                self._soltar_reclamo(fd_reclamo)
                with self.lock:
                    if self.running_job_id == job_id:
                        self.running_job_id = None
                self._barrido_si_toca()

    def _deadline_admision_vencido(self, project_id: str,
                                   job_id: str) -> bool:
        """HIGH-5: deadline de admisión agotado → failed durable."""
        try:
            with self.lock:
                job = self._load_job(project_id, job_id)
                if not job or job.get("state") != "queued":
                    return False
                deadline = job.get("admission_deadline")
                if not isinstance(deadline, str):
                    return False  # legado sin deadline: sin límite
                vencido = self.reloj() \
                    > datetime.fromisoformat(deadline)
                if vencido:
                    self._fallar(job, "admission_timeout",
                                 f"Plazo de admisión agotado "
                                 f"({ESPERA_ADMISION_S:.0f} s de cola, §J)")
                return vencido
        except (OSError, ValueError):
            return False

    def _cerrar_por_defecto(self, project_id: str, job_id: str,
                            exc: Exception) -> None:
        """HIGH-4: cierre durable del job no terminal que el defecto
        dejó colgado (queued, running o cancellation_pending — ronda
        adversarial); si el disco también falla, el arranque
        siguiente reconcilia (queued con registro se reencola)."""
        try:
            with self.lock:
                job = self._load_job(project_id, job_id)
                if job and job.get("state") in (
                        "queued", "running", "cancellation_pending"):
                    self._fallar(job, "worker_internal_error",
                                 f"Fallo inesperado del worker: {exc!r}")
        except OSError as exc_disco:
            print(f"jobs-worker: no se pudo cerrar {job_id}: "
                  f"{exc_disco!r}", file=sys.stderr, flush=True)

    @staticmethod
    def _extraer_salida(resp_json: Any) -> tuple[str, str]:
        """(contenido, finish_reason): forma cerrada y completitud."""
        choices = resp_json.get("choices") \
            if isinstance(resp_json, dict) else None
        if not isinstance(choices, list) or not choices \
                or not isinstance(choices[0], dict):
            _error(502, "backend_shape", "respuesta del backend sin choices")
        message = choices[0].get("message")
        contenido = message.get("content") \
            if isinstance(message, dict) else None
        finish_reason = choices[0].get("finish_reason")
        if not isinstance(contenido, str) or not isinstance(finish_reason, str):
            _error(502, "backend_shape", "respuesta del backend ilegible")
        if finish_reason != "stop":
            _error(502, "incomplete_output",
                   f"salida incompleta del backend "
                   f"(finish_reason={finish_reason})")
        return contenido, finish_reason

    def _vencido(self, job: dict, ahora: datetime | None = None) -> bool:
        try:
            dt_exp = datetime.fromisoformat(job["expires_at"])
            return (ahora or self.reloj()) > dt_exp
        except (KeyError, TypeError, ValueError):
            return False

    def _recalcular_expiracion(self, job: dict) -> None:
        """§J: la retención del resultado cuenta desde el terminal."""
        try:
            ttl = int(job.get("ttl_seconds", DEFAULT_TTL_SECONDS))
        except (TypeError, ValueError):
            ttl = DEFAULT_TTL_SECONDS
        ttl = min(max(ttl, 60), MAX_TTL_SECONDS)
        job["expires_at"] = (
            self.reloj() + timedelta(seconds=ttl)
        ).isoformat()

    def _cerrar(self, job: dict, estado: str) -> None:
        """Terminal durable; recalcula expires_at (§J); un vencido
        no resucita: se purga."""
        # [HIGH ronda 3] Terminal: sale del registro de despachados.
        self._en_cola.discard(job.get("job_id"))
        if self._vencido(job):
            self._purgar_job(job)
            return
        job["state"] = estado
        job["completed_at"] = self.reloj().isoformat()
        self._recalcular_expiracion(job)
        self._save_job_atomically(job)

    def _fallar(self, job: dict, codigo: str, mensaje: str) -> None:
        job["result"] = None
        job["error"] = {"code": codigo, "message": mensaje}
        self._cerrar(job, "failed")

    def _execute_single_job(self, project_id: str, job_id: str) -> None:
        job = self._load_job(project_id, job_id)
        if not job:
            return
        if job.get("state") == "cancellation_pending":
            with self.lock:
                self._cerrar(job, "cancelled")
            return
        payload = job.get("payload", {})
        formato = payload.get("response_format") \
            if isinstance(payload, dict) else None
        try:
            url = f"{self.backend_url}/v1/chat/completions"
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url, data=req_data, headers={"Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=120.0) as resp:
                resp_json = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            with self.lock:
                self._fallar(job, f"http_{exc.code}",
                             f"Error del backend HTTP {exc.code}")
            return
        except Exception as exc:
            with self.lock:
                self._fallar(job, "execution_error",
                             f"Fallo ejecutando tarea en segundo plano: {exc}")
            return
        with self.lock:
            latest = self._load_job(project_id, job_id)
            if latest and latest.get("state") == "cancellation_pending":
                self._cerrar(latest, "cancelled")
                return
            if latest:
                job = latest
            # Validación en la frontera de salida (BLOCKER-1): si falla,
            # estado de fallo explícito, nunca succeeded. Un
            # response_format ilegible en disco tampoco rompe el worker.
            try:
                contenido, finish_reason = self._extraer_salida(resp_json)
                if formato is not None:
                    validar_salida(contenido, formato["json_schema"]["schema"])
            except ErrorV2 as exc:
                self._fallar(job, exc.code, exc.message)
                return
            except (KeyError, TypeError) as exc:
                self._fallar(job, "invalid_job_payload",
                             f"job con response_format ilegible: {exc}")
                return
            job["result"] = {"text": contenido,
                             "finish_reason": finish_reason,
                             "complete": finish_reason == "stop"}
            job["error"] = None
            self._cerrar(job, "succeeded")
