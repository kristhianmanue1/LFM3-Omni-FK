#!/usr/bin/env python3
"""Recuperación al arranque y purga de trabajos largos (Perfil J) — Fase I5.

Contrato: docs/contracts/perfiles-servicio-v2.md (§J)
Especificación: docs/specs/SPEC-i5-jobs.md
Decisión: docs/adr/ADR-012-trabajos-largos-persistencia-idempotencia.md
Expediente: docs/reviews/evidence/fix-i5-jobs-frontera/ (fix-i5)

Reorganización pura del intento 4 (§3.3 del estándar: mover sin
cambiar comportamiento): la recuperación al arranque y el barrido de
vencidos vivían en JobsManager y pasan a este módulo como mixin, con
los mismos nombres de método y los mismos cuerpos. JobsManager aporta
los atributos que estos métodos usan — storage, lock, work_queue,
_en_cola, data_dir, idemp_dir, fallos_purga, intervalo_barrido_s,
tmp_edad_s y _ultimo_barrido — y los helpers _cerrar, _load_job,
_vencido y _registro_confirma_admision.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import sys
import time


class JobsRecoveryMixin:
    """Recuperación fail-closed al arranque y barrido periódico (D4)."""

    def startup_recover(self) -> int:
        """Fail-closed al arrancar: running y cancellation_pending
        pasan a failed (MED-1, ronda 2: un crash en la ventana de
        cancelación no puede dejar el job abierto); queued con registro
        se reencola (§J); sin registro, no se ejecuta."""
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
                    if estado in ("running", "cancellation_pending"):
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
                            self._en_cola.add(data["job_id"])
                        else:
                            data["error"] = {
                                "code": "admission_unconfirmed", "message":
                                    "Admisión no confirmada: registro de "
                                    "idempotencia ausente"}
                            self._cerrar(data, "failed")
        return recuperados

    def _barrido_si_toca(self) -> None:
        """D4: barrido periódico dentro del bucle del worker, sin
        hilo nuevo: vencidos a tombstone, temporales huérfanos y
        claims sin dueño, bajo el cerrojo de instancia."""
        if time.monotonic() - self._ultimo_barrido < self.intervalo_barrido_s:
            return
        self._ultimo_barrido = time.monotonic()
        self._purgar_expirados()
        self.storage.limpiar_temporales(self.tmp_edad_s)
        self.storage.limpiar_claims_huerfanos()

    def _purgar_job(self, job: dict) -> None:
        """Tombstone durable sin payload (§J); la E/S vive en storage
        (reorganización pura del intento 3, §3.3 del estándar). El
        job sale del registro de despachados ([HIGH ronda 3])."""
        self._en_cola.discard(job.get("job_id"))
        self.storage.purgar_a_tombstone(job)

    def _purgar_expirados(self) -> int:
        """Barrido: vencidos a tombstone, registros vencidos fuera.
        Los fallos de disco del barrido también se cuentan y hacen
        rastro: es la vía principal de purga (D4, ronda adversarial)."""
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
                # [MED ronda 3] El snapshot del archivo pudo quedar
                # viejo (un worker pasó el job a running tras la
                # lectura): recargar estado y vencimiento bajo el
                # lock antes de purgar; un running jamás se purga.
                proj_id = data.get("project_id")
                job_id = data.get("job_id")
                if not isinstance(proj_id, str) \
                        or not isinstance(job_id, str):
                    continue
                try:
                    with self.lock:
                        actual = self._load_job(proj_id, job_id)
                        if actual is None \
                                or actual.get("state") in (
                                    "expired", "running") \
                                or not self._vencido(actual, ahora):
                            continue
                        self._purgar_job(actual)
                    purgados += 1
                except OSError as exc:
                    self.fallos_purga += 1
                    print(f"jobs: purga fallida de "
                          f"{data.get('job_id')}: {exc!r}",
                          file=sys.stderr, flush=True)
        for rec_file in self.idemp_dir.glob("*/*.json"):
            try:
                rec = json.loads(rec_file.read_text(encoding="utf-8"))
                if ahora > datetime.fromisoformat(rec["expires_at"]):
                    rec_file.unlink(missing_ok=True)
            except OSError as exc:
                self.fallos_purga += 1
                print(f"jobs: retiro fallido del registro "
                      f"{rec_file.name}: {exc!r}",
                      file=sys.stderr, flush=True)
            except Exception:
                continue
        return purgados
