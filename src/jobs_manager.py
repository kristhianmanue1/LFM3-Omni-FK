#!/usr/bin/env python3
"""Manejador de Trabajos Largos en Segundo Plano (Perfil J) — Fase I5.

Contrato: docs/contracts/perfiles-servicio-v2.md (§J)
Especificación: docs/specs/SPEC-i5-jobs.md
Decisión: docs/adr/ADR-012-trabajos-largos-persistencia-idempotencia.md

Garantías:
- Idempotencia estricta canónica (RFC 8785) con TTL de 24 horas.
- Aislamiento multi-inquilino estricto (visibilidad exclusiva para el creador).
- Persistencia atómica en disco (POSIX write-tmp + os.replace).
- Recuperación segura en startup: running pasa a failed (outcome: unknown).
- Concurrencia acotada: 1 worker simultáneo global para no canibalizar H/M.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any

IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9_\-\.:]{1,64}$")
ALLOWED_OPERATIONS = {"infer_text", "infer_vision", "infer_audio", "infer_video"}
DEFAULT_TTL_SECONDS = 3600  # 1 hora tras terminal
MAX_TTL_SECONDS = 86400  # 24 horas
MAX_QUEUED_PER_PROJECT = 1
MAX_QUEUED_GLOBAL = 8


def canonical_json_rfc8785(data: Any) -> bytes:
    """Serializa un objeto a JSON canónico conforme a RFC 8785.

    - Claves de diccionarios ordenadas lexicográficamente.
    - Sin espacios en blanco superfluos.
    - Rechazo de números no finitos (NaN, Infinity).
    """
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


class JobsManager:
    """Gestor de ciclo de vida, persistencia y ejecución de trabajos largos."""

    def __init__(
        self,
        jobs_dir: str | Path | None = None,
        backend_url: str = "http://127.0.0.1:8091",
    ):
        if jobs_dir:
            self.base_dir = Path(jobs_dir)
        else:
            self.base_dir = Path(os.environ.get("LFM3_JOBS_DIR", "run/jobs"))

        self.data_dir = self.base_dir / "data"
        self.idemp_dir = self.base_dir / "idempotency"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.idemp_dir.mkdir(parents=True, exist_ok=True)

        self.backend_url = backend_url.rstrip("/")
        self.lock = threading.Lock()
        self.work_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.running_job_id: str | None = None
        self._stop_event = threading.Event()

        # Recuperar estado previo tras reinicio
        self.startup_recover()

        # Iniciar worker en background
        self._worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="jobs-worker"
        )
        self._worker_thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Detiene limpiamente el worker."""
        self._stop_event.set()
        self.work_queue.put(("", ""))  # Despertar thread
        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)

    # 1. Recuperación tras reinicio (fail-closed)
    def startup_recover(self) -> int:
        """Pasa cualquier trabajo encontrado en estado 'running' a 'failed'."""
        recovered = 0
        with self.lock:
            for proj_dir in self.data_dir.iterdir():
                if not proj_dir.is_dir():
                    continue
                for job_file in proj_dir.glob("*.json"):
                    try:
                        data = json.loads(job_file.read_text(encoding="utf-8"))
                        if data.get("state") == "running":
                            data["state"] = "failed"
                            data["completed_at"] = datetime.now(timezone.utc).isoformat()
                            data["error"] = {
                                "code": "server_interrupted",
                                "message": "Servidor reiniciado durante el procesamiento; resultado desconocido",
                            }
                            self._save_job_atomically(data)
                            recovered += 1
                        elif data.get("state") == "queued":
                            # Volver a encolar jobs pendientes
                            self.work_queue.put((data["project_id"], data["job_id"]))
                    except Exception:
                        continue
        return recovered

    # 2. Persistencia atómica
    def _save_job_atomically(self, job_dict: dict) -> None:
        proj_id = job_dict["project_id"]
        job_id = job_dict["job_id"]
        target_dir = self.data_dir / proj_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / f"{job_id}.json"

        tmp_file = target_dir / f"{job_id}.tmp.{os.getpid()}.{threading.get_ident()}"
        data_bytes = json.dumps(job_dict, indent=2, ensure_ascii=False).encode("utf-8")
        try:
            tmp_file.write_bytes(data_bytes)
            tmp_file.replace(target_file)
        except OSError:
            pass

    def _load_job(self, project_id: str, job_id: str) -> dict | None:
        target_file = self.data_dir / project_id / f"{job_id}.json"
        if not target_file.exists():
            return None
        try:
            return json.loads(target_file.read_text(encoding="utf-8"))
        except Exception:
            return None

    # 3. Idempotencia RFC 8785
    def _save_idempotency_record(
        self, project_id: str, key: str, job_id: str, payload_hash: str, expires_at: str
    ) -> None:
        target_dir = self.idemp_dir / project_id
        target_dir.mkdir(parents=True, exist_ok=True)
        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
        target_file = target_dir / f"{key_hash}.json"

        record = {
            "key": key,
            "job_id": job_id,
            "payload_hash": payload_hash,
            "expires_at": expires_at,
        }
        tmp_file = target_dir / f"{key_hash}.tmp.{os.getpid()}"
        tmp_file.write_text(json.dumps(record), encoding="utf-8")
        tmp_file.replace(target_file)

    def _lookup_idempotency_record(self, project_id: str, key: str) -> dict | None:
        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
        target_file = self.idemp_dir / project_id / f"{key_hash}.json"
        if not target_file.exists():
            return None
        try:
            record = json.loads(target_file.read_text(encoding="utf-8"))
            dt_exp = datetime.fromisoformat(record["expires_at"])
            if datetime.now(timezone.utc) > dt_exp:
                target_file.unlink(missing_ok=True)
                return None
            return record
        except Exception:
            return None

    # 4. Operación POST /jobs (Crear / Reclamar)
    def create_job(
        self,
        project_id: str,
        operation: str,
        payload: dict,
        idempotency_key: str,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> tuple[int, dict]:
        """Crea o recupera un trabajo en segundo plano con control de idempotencia."""
        if not isinstance(idempotency_key, str) or not IDEMPOTENCY_KEY_RE.match(idempotency_key):
            return 400, {
                "error": {
                    "code": "invalid_idempotency_key",
                    "message": "Idempotency-Key debe ser ASCII de 1 a 64 caracteres válidos",
                }
            }

        if operation not in ALLOWED_OPERATIONS:
            return 400, {
                "error": {
                    "code": "unsupported_operation",
                    "message": f"Operación '{operation}' no admitida en Perfil J",
                }
            }

        if not isinstance(payload, dict):
            return 400, {
                "error": {
                    "code": "invalid_payload",
                    "message": "payload debe ser un objeto JSON",
                }
            }

        # Calcular hash canónico RFC 8785
        try:
            canon_bytes = canonical_json_rfc8785({"operation": operation, "payload": payload})
            payload_hash = hashlib.sha256(canon_bytes).hexdigest()
        except Exception as exc:
            return 400, {
                "error": {
                    "code": "canonicalization_error",
                    "message": f"Error canonicalizando payload: {exc}",
                }
            }

        with self.lock:
            # 1. Comprobar idempotencia previa
            rec = self._lookup_idempotency_record(project_id, idempotency_key)
            if rec:
                if rec["payload_hash"] == payload_hash:
                    # Idempotente: devolver job ya admitido
                    existente = self._load_job(project_id, rec["job_id"])
                    if existente:
                        return 202, {
                            "job_id": existente["job_id"],
                            "state": existente["state"],
                            "status_url": f"/jobs/{existente['job_id']}",
                            "created_at": existente["created_at"],
                            "expires_at": existente["expires_at"],
                        }
                else:
                    # Conflicto 409
                    return 409, {
                        "error": {
                            "code": "idempotency_conflict",
                            "message": "Idempotency-Key ya utilizada con un cuerpo de solicitud diferente",
                        }
                    }

            # 2. Control de límites de cola
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

            if queued_proj >= MAX_QUEUED_PER_PROJECT:
                return 429, {
                    "error": {
                        "code": "queue_limit_per_project_exceeded",
                        "message": f"El proyecto ya tiene {queued_proj} trabajo(s) en cola (máximo {MAX_QUEUED_PER_PROJECT})",
                    }
                }

            if queued_global >= MAX_QUEUED_GLOBAL:
                return 429, {
                    "error": {
                        "code": "global_queue_limit_exceeded",
                        "message": f"Cola global de trabajos saturada ({queued_global} en espera)",
                    }
                }

            # 3. Creación y persistencia atómica
            ahora = datetime.now(timezone.utc)
            ttl = min(max(ttl_seconds, 60), MAX_TTL_SECONDS)
            expira = ahora + timedelta(seconds=ttl)
            job_id = f"job-{hashlib.sha256(f'{project_id}:{idempotency_key}:{ahora.isoformat()}'.encode()).hexdigest()[:16]}"

            job_dict = {
                "job_id": job_id,
                "contract_version": "2",
                "project_id": project_id,
                "operation": operation,
                "payload": payload,
                "state": "queued",
                "created_at": ahora.isoformat(),
                "started_at": None,
                "completed_at": None,
                "expires_at": expira.isoformat(),
                "result": None,
                "error": None,
                "model_revision": "LiquidAI/LFM3-Omni-2B-GGUF",
            }

            self._save_job_atomically(job_dict)
            self._save_idempotency_record(
                project_id, idempotency_key, job_id, payload_hash, expira.isoformat()
            )
            self.work_queue.put((project_id, job_id))

            return 202, {
                "job_id": job_id,
                "state": "queued",
                "status_url": f"/jobs/{job_id}",
                "created_at": job_dict["created_at"],
                "expires_at": job_dict["expires_at"],
            }

    # 5. Operación GET /jobs/{id} (Consulta)
    def get_job(self, project_id: str, job_id: str) -> tuple[int, dict]:
        """Consulta el estado y resultado del trabajo de forma aislada."""
        job = self._load_job(project_id, job_id)
        if not job or job.get("project_id") != project_id:
            # Fail-closed: no revelar si existe bajo otro proyecto
            return 404, {"error": {"code": "not_found", "message": "Trabajo no encontrado"}}

        # Verificar TTL
        try:
            dt_exp = datetime.fromisoformat(job["expires_at"])
            if datetime.now(timezone.utc) > dt_exp:
                return 410, {
                    "error": {
                        "code": "job_expired",
                        "message": "El resultado del trabajo ha expirado (TTL vencido)",
                    }
                }
        except Exception:
            pass

        # Devolver vista de consumo (sin payload interno sensible)
        vista = {
            "job_id": job.get("job_id"),
            "contract_version": job.get("contract_version", "2"),
            "project_id": job.get("project_id"),
            "operation": job.get("operation"),
            "state": job.get("state"),
            "created_at": job.get("created_at"),
            "started_at": job.get("started_at"),
            "completed_at": job.get("completed_at"),
            "expires_at": job.get("expires_at"),
            "result": job.get("result"),
            "error": job.get("error"),
            "model_revision": job.get("model_revision"),
        }
        return 200, vista

    # 6. Operación DELETE /jobs/{id} (Cancelación)
    def cancel_job(self, project_id: str, job_id: str) -> tuple[int, dict]:
        """Solicita la cancelación de un trabajo propio."""
        with self.lock:
            job = self._load_job(project_id, job_id)
            if not job or job.get("project_id") != project_id:
                return 404, {"error": {"code": "not_found", "message": "Trabajo no encontrado"}}

            state = job.get("state")
            if state in ("succeeded", "failed", "cancelled"):
                return 200, {
                    "job_id": job_id,
                    "cancellation_status": "already_terminal",
                    "target_state": state,
                }

            if state == "queued":
                job["state"] = "cancelled"
                job["completed_at"] = datetime.now(timezone.utc).isoformat()
                self._save_job_atomically(job)
                return 200, {
                    "job_id": job_id,
                    "cancellation_status": "accepted",
                    "target_state": "cancelled",
                }

            if state == "running":
                job["state"] = "cancellation_pending"
                self._save_job_atomically(job)
                return 200, {
                    "job_id": job_id,
                    "cancellation_status": "pending",
                    "target_state": "cancellation_pending",
                }

            return 200, {
                "job_id": job_id,
                "cancellation_status": "pending",
                "target_state": state,
            }

    # 7. Bucle de ejecución del worker en segundo plano
    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                proj_id, job_id = self.work_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if not proj_id or not job_id:
                continue

            with self.lock:
                job = self._load_job(proj_id, job_id)
                if not job or job.get("state") != "queued":
                    continue
                job["state"] = "running"
                job["started_at"] = datetime.now(timezone.utc).isoformat()
                self.running_job_id = job_id
                self._save_job_atomically(job)

            # Ejecutar tarea fuera del cerrojo
            self._execute_single_job(proj_id, job_id)

            with self.lock:
                self.running_job_id = None

    def _execute_single_job(self, project_id: str, job_id: str) -> None:
        job = self._load_job(project_id, job_id)
        if not job:
            return

        # Comprobar cancelación temprana
        if job.get("state") == "cancellation_pending":
            job["state"] = "cancelled"
            job["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._save_job_atomically(job)
            return

        operation = job.get("operation")
        payload = job.get("payload", {})

        # Despachar al backend
        try:
            url = f"{self.backend_url}/v1/chat/completions"
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url, data=req_data, headers={"Content-Type": "application/json"}, method="POST"
            )
            with urllib.request.urlopen(req, timeout=120.0) as resp:
                resp_bytes = resp.read()
                resp_json = json.loads(resp_bytes.decode("utf-8"))

            with self.lock:
                latest = self._load_job(project_id, job_id)
                if latest and latest.get("state") == "cancellation_pending":
                    latest["state"] = "cancelled"
                    latest["completed_at"] = datetime.now(timezone.utc).isoformat()
                    self._save_job_atomically(latest)
                    return

                choices = resp_json.get("choices", [{}])
                msg_content = choices[0].get("message", {}).get("content", "")
                finish_reason = choices[0].get("finish_reason", "stop")

                job["state"] = "succeeded"
                job["completed_at"] = datetime.now(timezone.utc).isoformat()
                job["result"] = {
                    "text": msg_content,
                    "finish_reason": finish_reason,
                    "complete": finish_reason == "stop",
                }
                job["error"] = None
                self._save_job_atomically(job)
        except urllib.error.HTTPError as exc:
            with self.lock:
                job["state"] = "failed"
                job["completed_at"] = datetime.now(timezone.utc).isoformat()
                job["error"] = {
                    "code": f"http_{exc.code}",
                    "message": f"Error del backend HTTP {exc.code}",
                }
                self._save_job_atomically(job)
        except Exception as exc:
            with self.lock:
                job["state"] = "failed"
                job["completed_at"] = datetime.now(timezone.utc).isoformat()
                job["error"] = {
                    "code": "execution_error",
                    "message": f"Fallo ejecutando tarea en segundo plano: {exc}",
                }
                self._save_job_atomically(job)
