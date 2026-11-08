#!/usr/bin/env python3
"""Persistencia durable de trabajos largos (Perfil J) — Fase I5.

Contrato: docs/contracts/perfiles-servicio-v2.md (§J)
Especificación: docs/specs/SPEC-i5-jobs.md §4
Decisión: docs/adr/ADR-012-trabajos-largos-persistencia-idempotencia.md
Expediente: docs/reviews/evidence/fix-i5-jobs-frontera/ (fix-i5)

Todo el árbol run/jobs pasa por aquí: datos de jobs, registros de
idempotencia y cerrojos de reclamo. Garantías: escritura atómica
durable (tmp 0600, bucle de escritura, fsync de archivo, os.replace y
fsync de directorio) sin tragarse OSError — nada se reporta si no
consta en disco (BLOCKER-2 del expediente); commit del registro de
idempotencia por link exclusivo (el registro ES la admisión); permisos
0700/0600 para confidencialidad (§J).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import threading

TOMBSTONE_IDEMP_HORAS = 24  # ventana de deduplicación de §J


class JobsStorage:
    """E/S durable del árbol run/jobs: data, idempotency y claims."""

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.idemp_dir = self.base_dir / "idempotency"
        self.claims_dir = self.base_dir / "claims"
        for directorio in (self.base_dir, self.data_dir, self.idemp_dir):
            directorio.mkdir(parents=True, exist_ok=True)
            os.chmod(directorio, 0o700)  # confidencialidad (§J)

    def volcar_tmp_durable(self, directorio: Path, nombre: str,
                           datos: bytes) -> Path:
        """tmp 0600 con fsync; el fallo limpia el tmp y propaga."""
        directorio.mkdir(parents=True, exist_ok=True)
        os.chmod(directorio, 0o700)
        tmp = directorio / f"{nombre}.tmp.{os.getpid()}.{threading.get_ident()}"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            vista = memoryview(datos)
            while vista:
                vista = vista[os.write(fd, vista):]
            os.fsync(fd)
        except OSError:
            os.close(fd)
            tmp.unlink(missing_ok=True)
            raise
        os.close(fd)
        return tmp

    def fsync_directorio(self, directorio: Path) -> None:
        dfd = os.open(directorio, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)

    def reemplazar_durable(self, tmp: Path, destino: Path) -> None:
        try:
            os.replace(tmp, destino)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise
        self.fsync_directorio(destino.parent)

    def save_job(self, job_dict: dict) -> None:
        """Job durable: tmp 0600 + fsync + rename + fsync de directorio.
        Los fallos de E/S se propagan: nada se reporta sin que conste."""
        target_dir = self.data_dir / job_dict["project_id"]
        target_file = target_dir / f"{job_dict['job_id']}.json"
        datos = json.dumps(
            job_dict, indent=2, ensure_ascii=False).encode("utf-8")
        tmp = self.volcar_tmp_durable(target_dir, target_file.name, datos)
        self.reemplazar_durable(tmp, target_file)

    def load_job(self, project_id: str, job_id: str) -> dict | None:
        target_file = self.data_dir / project_id / f"{job_id}.json"
        if not target_file.exists():
            return None
        try:
            return json.loads(target_file.read_text(encoding="utf-8"))
        except Exception:
            return None

    def eliminar_job(self, project_id: str, job_id: str) -> None:
        """Best-effort: sin commit de registro no hay job; el arranque
        reconcilia cualquier resto (no se ejecuta)."""
        try:
            (self.data_dir / project_id / f"{job_id}.json").unlink(
                missing_ok=True)
        except OSError:
            pass

    def commit_registro_idempotencia(self, project_id: str, key: str,
                                     job_id: str, payload_hash: str):
        """Registro exclusivo: tmp durable + os.link. Vive
        TOMBSTONE_IDEMP_HORAS (ventana de deduplicación de §J)."""
        target_dir = self.idemp_dir / project_id
        target_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(target_dir, 0o700)
        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
        target_file = target_dir / f"{key_hash}.json"
        expiracion = (datetime.now(timezone.utc)
                      + timedelta(hours=TOMBSTONE_IDEMP_HORAS)).isoformat()
        record = {"key": key, "job_id": job_id,
                  "payload_hash": payload_hash, "expires_at": expiracion}
        tmp = self.volcar_tmp_durable(target_dir, target_file.name,
                                      json.dumps(record).encode())
        try:
            os.link(tmp, target_file)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise
        tmp.unlink(missing_ok=True)
        self.fsync_directorio(target_dir)

    def lookup_idempotency_record(self, project_id: str,
                                  key: str) -> dict | None:
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

    def asegurar_claims_dir(self) -> Path:
        """Crea claims/ on demand con permisos 0700 (§J)."""
        self.claims_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.claims_dir, 0o700)
        return self.claims_dir

    def eliminar_claim(self, job_id: str) -> None:
        """Retira el cerrojo de reclamo de un job (purga)."""
        try:
            (self.claims_dir / f"{job_id}.lock").unlink(missing_ok=True)
        except OSError:
            pass
