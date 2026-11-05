"""Retención privada de transcripciones por turno — TAREA I1-VT (D-10).

D-10 (Operador, aceptada 2026-11-04): las sesiones personales de voz
dejan transcripción de entrada y respuesta asociadas por turno, con
timestamps y parámetros/hashes, en archivos JSONL 0600 bajo
docs/reviews/evidence/privado/transcripciones/ (excluido de Git por
.gitignore; «privado» también está fuera del gate de tamaños). No se
conserva audio ni video; no hay borrado automático acordado; antes de
publicar cualquier extracto se sanea y revisa con el Operador.

Fail-closed: texto vacío o de tipo incorrecto, o una sesión mal
formada o fuera de la raíz privada, lanzan ValueError sin escribir
nada. La retención fallida debe interrumpir la sesión (no saltarse en
silencio): es la promesa de auditoría de D-10.

Identificadores y claves en inglés (estándar §3.1, ADR-015; el legado
en español de src/ no es precedente para código nuevo).
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = (Path(__file__).resolve().parent.parent
        / "docs/reviews/evidence/privado/transcripciones")
DIR_MODE = 0o700
FILE_MODE = 0o600


def _validate_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}: se exige texto no vacío")
    return value


def new_session(root=None):
    """Crea la raíz privada (0700, umask-independiente) si falta y
    devuelve la ruta absoluta de una sesión nueva. El nombre lleva
    timestamp UTC y un sufijo aleatorio (sin colisión por segundo)."""
    root = Path(root).resolve() if root is not None else ROOT
    root.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
    os.chmod(root, DIR_MODE)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return root / f"session-{ts}-{os.urandom(3).hex()}.jsonl"


def record_turn(session, *, user_text, reply, params=None, hashes=None,
                root=None):
    """Añade un turno como línea JSONL: ts UTC, user_text, reply,
    params y hashes. Sólo texto y hashes (nunca audio, D-10).

    La sesión debe vivir dentro de la raíz privada (la pasada o la por
    defecto): se rechaza cualquier ruta fuera de ella."""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "user_text": _validate_text(user_text, "user_text"),
        "reply": _validate_text(reply, "reply"),
        "params": dict(params or {}),
        "hashes": dict(hashes or {}),
    }
    root = Path(root).resolve() if root is not None else ROOT
    session = Path(session)
    if not session.is_absolute():
        raise ValueError("session: se exige ruta absoluta (usa new_session)")
    if root not in session.resolve().parents:
        raise ValueError("session: fuera de la raíz privada de D-10")
    if not session.parent.is_dir():
        raise ValueError("session: el directorio no existe (usa new_session)")
    if session.suffix != ".jsonl":
        raise ValueError("session: se exige archivo .jsonl")
    if session.exists():
        os.chmod(session, FILE_MODE)  # corrige permisos antes de escribir
    line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(session, os.O_WRONLY | os.O_CREAT | os.O_APPEND, FILE_MODE)
    try:
        pending = memoryview(line)
        while pending:  # POSIX permite escrituras cortas
            pending = pending[os.write(fd, pending):]
    finally:
        os.close(fd)
    os.chmod(session, FILE_MODE)
    return record
