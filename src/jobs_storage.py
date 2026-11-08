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
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time

TOMBSTONE_IDEMP_HORAS = 24  # ventana de deduplicación de §J


class CommitTrasLinkError(OSError):
    """El registro de idempotencia quedó enlazado pero un paso
    posterior (unlink del tmp, fsync del directorio) falló.

    BLOCKER-1 del expediente: la operación tiene resultado incierto —
    el commit es visible aunque no conste durable. Quien la reciba
    debe reconciliar registro y job antes de responder o de admitir
    reintentos, jamás descartar el registro a ciegas.
    """


class JobsDirOcupado(RuntimeError):
    """Otra instancia sostiene el cerrojo de este jobs_dir (D1).

    La topología autorizada es UNA instancia por jobs_dir: el cerrojo
    se toma con flock exclusivo y no bloqueante al arrancar y una
    segunda instancia falla cerrada sin arrancar worker ni
    recuperación. El mensaje nombra el directorio y la causa.
    """


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
        reconcilia cualquier resto (no se ejecuta). Un fallo del
        unlink queda visible: un huérfano queued bloquearía el
        proyecto con 429 hasta el reinicio (ronda adversarial)."""
        try:
            (self.data_dir / project_id / f"{job_id}.json").unlink(
                missing_ok=True)
        except OSError as exc:
            print(f"jobs: no se pudo retirar el job sin admisión "
                  f"{project_id}/{job_id}: {exc!r}",
                  file=sys.stderr, flush=True)

    def commit_registro_idempotencia(self, project_id: str, key: str,
                                     job_id: str, payload_hash: str):
        """Registro exclusivo: tmp durable + os.link. Vive
        TOMBSTONE_IDEMP_HORAS (ventana de deduplicación de §J).
        Un fallo tras el link se reporta como CommitTrasLinkError:
        el resultado del commit es incierto y exige reconciliación."""
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
        try:
            tmp.unlink(missing_ok=True)
            self.fsync_directorio(target_dir)
        except OSError as exc:
            raise CommitTrasLinkError(
                f"registro enlazado sin confirmación durable para "
                f"{project_id}: {exc}") from exc

    def retirar_registro(self, project_id: str, key: str) -> bool:
        """True si el registro NO está en disco tras la llamada (no
        existía o el unlink tuvo éxito); False si sigue presente.

        El fsync del directorio tras el unlink es best-effort: si
        falla, el archivo ya no está para este proceso — el reintento
        readmite sin duplicar — y ante crash del host un registro
        reaparecido queda como huérfano, que la frontera reconcilia
        (BLOCKER-1). Confundir ese caso con «no pude borrarlo» fue el
        BLOCKER de la ronda adversarial: devolver False con el
        registro ya ausente fabrica un 202 sin registro.
        """
        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
        target_file = self.idemp_dir / project_id / f"{key_hash}.json"
        try:
            target_file.unlink(missing_ok=True)
        except OSError:
            return False
        try:
            self.fsync_directorio(target_file.parent)
        except OSError:
            pass  # best-effort; ver docstring
        return True

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

    def tomar_cerrojo_instancia(self) -> int:
        """flock exclusivo y no bloqueante sobre el jobs_dir (D1).

        Devuelve el fd que sostiene el cerrojo; lanza
        JobsDirOcupado nombrando el directorio y la causa si otra
        instancia lo tiene.
        """
        lock_path = self.base_dir / ".instance.lock"
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise JobsDirOcupado(
                f"jobs_dir {self.base_dir} ya está en uso por otra "
                f"instancia; no se arrancan worker ni recuperación "
                f"(flock: {exc})") from exc
        return fd

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

    def limpiar_temporales(self, tmp_edad_s: float) -> None:
        """Temporales huérfanos (*.tmp.*) fuera tras tmp_edad_s: un
        tmp legítimo vive milisegundos; uno viejo es basura de un
        crash y puede llevar datos sensibles del cliente (HIGH-6)."""
        limite = time.time() - tmp_edad_s
        for base in (self.data_dir, self.idemp_dir):
            if not base.exists():
                continue
            for tmp in base.rglob("*.tmp.*"):
                try:
                    if tmp.is_file() and tmp.stat().st_mtime < limite:
                        tmp.unlink()
                except OSError:
                    continue

    def limpiar_claims_huerfanos(self) -> None:
        """Claims de jobs inexistentes o terminales fuera; el claim
        de un ejecutor vivo (flock sostenido) se respeta (HIGH-6)."""
        if not self.claims_dir.exists():
            return
        for lock in list(self.claims_dir.glob("*.lock")):
            job_id = lock.stem
            coincidencias = list(self.data_dir.rglob(f"{job_id}.json"))
            terminal = True
            if coincidencias:
                try:
                    data = json.loads(
                        coincidencias[0].read_text(encoding="utf-8"))
                    terminal = data.get("state") in (
                        "succeeded", "failed", "cancelled", "expired")
                except Exception:
                    terminal = False  # ilegible: no tocar
            if not terminal:
                continue
            try:
                fd = os.open(lock, os.O_RDWR)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    os.close(fd)
                    continue  # un ejecutor lo sostiene
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
                lock.unlink(missing_ok=True)
            except OSError:
                continue
