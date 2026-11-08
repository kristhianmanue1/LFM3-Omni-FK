#!/usr/bin/env python3
"""Manejador de Trabajos Largos en Segundo Plano (Perfil J) — Fase I5.

Contrato: docs/contracts/perfiles-servicio-v2.md (§J)
Especificación: docs/specs/SPEC-i5-jobs.md
Decisión: docs/adr/ADR-012-trabajos-largos-persistencia-idempotencia.md
Expediente: docs/reviews/evidence/fix-i5-jobs-frontera/ (fix-i5)

Garantías: idempotencia canónica RFC 8785 con tombstone 24 h (§J);
persistencia atómica durable en jobs_storage (el registro de
idempotencia es el commit de la admisión); recuperación fail-closed;
reclamo atómico entre procesos (flock) con admisión compartida con
H/M; salida del modelo validada (completitud y esquema) antes de
persistir; retención §J con purga verificable y permisos 0600/0700.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
from jobs_storage import JobsStorage

IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9_\-\.:]{1,64}$")
ALLOWED_OPERATIONS = {"infer_text", "infer_vision", "infer_audio", "infer_video"}
DEFAULT_TTL_SECONDS = 3600  # 1 hora tras terminal (§J)
MAX_TTL_SECONDS = 86400  # 24 horas
MAX_QUEUED_PER_PROJECT = 1
MAX_QUEUED_GLOBAL = 8
ADMISION_TIMEOUT_S = 60.0  # presupuesto de cola compartido (§J)
REINTENTO_ADMISION_S = 0.5
MSG_IDEMPOTENCY_CONFLICT = (
    "Idempotency-Key ya utilizada con un cuerpo de solicitud diferente")


def _respuesta_error(status: int, code: str, message: str) -> tuple[int, dict]:
    """Cuerpo de error homogéneo (la frontera HTTP lo reenvía)."""
    return status, {"error": {"code": code, "message": message}}


class JobsManager:
    """Gestor de ciclo de vida, persistencia y ejecución de trabajos largos."""

    def __init__(self, jobs_dir: str | Path | None = None,
                 backend_url: str = "http://127.0.0.1:8091",
                 dispatcher: Any = None,
                 rate_limit_lookup: Callable[[str], dict] | None = None):
        if jobs_dir:
            base_dir = Path(jobs_dir)
        else:
            base_dir = Path(os.environ.get("LFM3_JOBS_DIR", "run/jobs"))
        self.storage = JobsStorage(base_dir)
        self.data_dir = self.storage.data_dir
        self.idemp_dir = self.storage.idemp_dir
        self.claims_dir = self.storage.claims_dir
        self.backend_url = backend_url.rstrip("/")
        # Admisión compartida con H/M (HIGH-1); None = sin (tests).
        self.dispatcher = dispatcher
        self.rate_limit_lookup = rate_limit_lookup
        self.lock = threading.Lock()
        self.work_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.running_job_id: str | None = None
        self._stop_event = threading.Event()
        self.startup_recover()
        self._worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="jobs-worker")
        self._worker_thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Detiene limpiamente el worker."""
        self._stop_event.set()
        self.work_queue.put(("", ""))  # Despertar thread
        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)

    def startup_recover(self) -> int:
        """Fail-closed al arrancar: running pasa a failed; queued con
        registro se reencola (§J); sin registro, no se ejecuta."""
        recuperados = 0
        self._purgar_expirados()
        with self.lock:
            for proj_dir in sorted(self.data_dir.iterdir()):
                if not proj_dir.is_dir():
                    continue
                for job_file in sorted(proj_dir.glob("*.json")):
                    try:
                        data = json.loads(job_file.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    estado = data.get("state")
                    if estado == "running":
                        data["error"] = {
                            "code": "server_interrupted", "message":
                                "Servidor reiniciado durante el procesamiento; "
                                "resultado desconocido"}
                        self._cerrar(data, "failed")
                        recuperados += 1
                    elif estado == "queued":
                        if self._registro_confirma_admision(data):
                            self.work_queue.put(
                                (data["project_id"], data["job_id"]))
                        else:
                            data["error"] = {
                                "code": "admission_unconfirmed", "message":
                                    "Admisión no confirmada: registro de "
                                    "idempotencia ausente"}
                            self._cerrar(data, "failed")
        return recuperados

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
        if operation not in ALLOWED_OPERATIONS:
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
                if existente is None \
                        or existente.get("state") == "expired" \
                        or self._vencido(existente):
                    # Registro vivo con resultado caducado: dentro del
                    # tombstone nunca se re-infiera (§J).
                    return _respuesta_error(
                        410, "job_expired",
                        "El trabajo asociado a esta clave ya expiró; "
                        "use una clave nueva")
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
            ahora = datetime.now(timezone.utc)
            ttl = ttl_seconds if isinstance(ttl_seconds, int) \
                and not isinstance(ttl_seconds, bool) else DEFAULT_TTL_SECONDS
            ttl = min(max(ttl, 60), MAX_TTL_SECONDS)
            expira = ahora + timedelta(seconds=ttl)
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
                "result": None,
                "error": None,
                "model_revision": "LiquidAI/LFM3-Omni-2B-GGUF",
            }
            try:
                self._save_job_atomically(job_dict)
            except OSError:
                return _respuesta_error(
                    500, "storage_error",
                    "No se pudo persistir el trabajo; admisión denegada")
            try:
                self.storage.commit_registro_idempotencia(
                    project_id, idempotency_key, job_id, payload_hash)
            except FileExistsError:
                return self._resolver_rival(
                    project_id, idempotency_key, payload_hash, job_id)
            except OSError:
                self._descartar_job_sin_admision(project_id, job_id)
                return _respuesta_error(
                    500, "storage_error",
                    "No se pudo persistir el registro de idempotencia; "
                    "admisión denegada")
            self.work_queue.put((project_id, job_id))
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
        return 202, self._vista_admision(existente)

    @staticmethod
    def _vista_admision(job: dict) -> dict:
        """Respuesta 202 de admisión (SPEC-i5 §2.1)."""
        return {
            "job_id": job["job_id"], "state": job["state"],
            "status_url": f"/jobs/{job['job_id']}",
            "created_at": job["created_at"], "expires_at": job["expires_at"]}

    def _contar_encolados(self, project_id: str) -> tuple[int, int]:
        """(no terminales del proyecto, globales) según disco; contar
        running cierra la carrera reclamo-vs-admisión (SPEC-i5 §2.1)."""
        queued_proj = 0
        queued_global = 0
        OCUPADOS = ("queued", "running", "cancellation_pending")
        for p_dir in self.data_dir.iterdir():
            if not p_dir.is_dir():
                continue
            for f_job in p_dir.glob("*.json"):
                try:
                    j_data = json.loads(f_job.read_text(encoding="utf-8"))
                    if j_data.get("state") in OCUPADOS:
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
            if job.get("state") not in ("running", "expired"):
                try:
                    self._purgar_job(job)
                except OSError:
                    pass  # el 410 sigue siendo cierto; la purga reintenta
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
        por job; fd o None si lo tiene otro, no está en cola o venció."""
        try:
            claims_dir = self.storage.asegurar_claims_dir()
            fd = os.open(claims_dir / f"{job_id}.lock",
                         os.O_RDWR | os.O_CREAT, 0o600)
        except OSError:
            return None
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return None
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
        ventana). Job ilegible: se salta sin romper el worker."""
        with self.lock:
            try:
                job = self._load_job(project_id, job_id)
                if not job or job.get("state") != "queued":
                    return False
                job["state"] = "running"
                job["started_at"] = datetime.now(timezone.utc).isoformat()
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
                continue
            if not proj_id or not job_id:
                continue
            fd_reclamo = self._reclamar(proj_id, job_id)
            if fd_reclamo is None:
                continue
            try:
                if not self._admitir(proj_id):
                    # Sin presupuesto: vuelve a la cola y se reintenta
                    # tras una pausa; nunca se ejecuta sin admisión.
                    self.work_queue.put((proj_id, job_id))
                    self._stop_event.wait(REINTENTO_ADMISION_S)
                    continue
                try:
                    if self._marcar_running(proj_id, job_id):
                        self._execute_single_job(proj_id, job_id)
                finally:
                    self._liberar_admision(proj_id)
            except OSError:
                # Persistencia fallida: el disco manda (fail-closed).
                continue
            except Exception as exc:
                # Defecto inesperado (dispatcher mal cableado): el worker
                # sobrevive y el reclamo se libera siempre (stderr visible).
                print(f"jobs-worker: fallo inesperado en {job_id}: {exc!r}",
                      file=sys.stderr, flush=True)
                continue
            finally:
                self._soltar_reclamo(fd_reclamo)
                with self.lock:
                    if self.running_job_id == job_id:
                        self.running_job_id = None

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
            return (ahora or datetime.now(timezone.utc)) > dt_exp
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
            datetime.now(timezone.utc) + timedelta(seconds=ttl)
        ).isoformat()

    def _purgar_job(self, job: dict) -> None:
        """Tombstone durable sin payload ni resultado: registra el
        borrado (§J) y retira el cerrojo de reclamo."""
        ahora = datetime.now(timezone.utc)
        job_id = job.get("job_id") or "desconocido"
        tombstone = {
            "job_id": job_id,
            "contract_version": job.get("contract_version", "2"),
            "project_id": job.get("project_id"),
            "state": "expired",
            "expires_at": job.get("expires_at"),
            "created_at": job.get("created_at"),
            "expired_at": job.get("expires_at"),
            "purged_at": ahora.isoformat(),
            "model_revision": job.get("model_revision"),
        }
        self._save_job_atomically(tombstone)
        self.storage.eliminar_claim(job_id)

    def _purgar_expirados(self) -> int:
        """Barrido: vencidos a tombstone, registros vencidos fuera."""
        purgados = 0
        ahora = datetime.now(timezone.utc)
        for proj_dir in self.data_dir.glob("*"):
            if not proj_dir.is_dir():
                continue
            for job_file in proj_dir.glob("*.json"):
                try:
                    data = json.loads(job_file.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if data.get("state") in ("expired", "running"):
                    continue  # tombstone hecho; en vuelo, no tocar
                if not self._vencido(data, ahora):
                    continue
                try:
                    self._purgar_job(data)
                    purgados += 1
                except OSError:
                    continue
        for rec_file in self.idemp_dir.glob("*/*.json"):
            try:
                rec = json.loads(rec_file.read_text(encoding="utf-8"))
                if ahora > datetime.fromisoformat(rec["expires_at"]):
                    rec_file.unlink(missing_ok=True)
            except Exception:
                continue
        return purgados

    def _cerrar(self, job: dict, estado: str) -> None:
        """Terminal durable; recalcula expires_at (§J); un vencido
        no resucita: se purga."""
        if self._vencido(job):
            self._purgar_job(job)
            return
        job["state"] = estado
        job["completed_at"] = datetime.now(timezone.utc).isoformat()
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
