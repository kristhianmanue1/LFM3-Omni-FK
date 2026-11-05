"""Pruebas de la retención privada de transcripciones (TAREA I1-VT, D-10).

D-10 aceptada (Operador, 2026-11-04): cada turno de una sesión personal
deja transcripción de entrada y respuesta asociadas, con timestamps y
parámetros/hashes, en archivos 0600 bajo
docs/reviews/evidence/privado/transcripciones/ (excluido de Git). No se
conserva audio ni video; sin borrado automático; fail-closed: texto
vacío, tipo incorrecto o sesión fuera de la raíz no escriben nada.
"""

import importlib.util
import json
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PRIVATE = RAIZ / "docs/reviews/evidence/privado/transcripciones"


def _load():
    spec = importlib.util.spec_from_file_location(
        "transcripciones", RAIZ / "src/transcripciones.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class TurnRetention(unittest.TestCase):
    def test_full_turn_leaves_0600_jsonl_with_both_texts(self):
        t = _load()
        with tempfile.TemporaryDirectory() as tmp:
            session = t.new_session(Path(tmp))
            t.record_turn(
                session, user_text="hola, ¿qué tal?", reply="muy bien",
                params={"model": "Q4_K_M", "max_tokens": 100},
                hashes={"input_audio": "00" * 32}, root=Path(tmp))
            self.assertTrue(session.is_file())
            self.assertEqual(oct(session.stat().st_mode & 0o777), oct(0o600))
            line = json.loads(session.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(line["user_text"], "hola, ¿qué tal?")
            self.assertEqual(line["reply"], "muy bien")
            self.assertEqual(line["params"]["max_tokens"], 100)
            self.assertEqual(line["hashes"]["input_audio"], "00" * 32)
            datetime.fromisoformat(line["ts"])  # timestamp ISO parseable

    def test_several_turns_append_in_order(self):
        t = _load()
        with tempfile.TemporaryDirectory() as tmp:
            session = t.new_session(Path(tmp))
            for i in range(3):
                t.record_turn(session, user_text=f"turno {i}",
                              reply=f"respuesta {i}", root=Path(tmp))
            lines = [json.loads(l) for l in
                     session.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([l["user_text"] for l in lines],
                             ["turno 0", "turno 1", "turno 2"])

    def test_sessions_do_not_collide_within_the_same_second(self):
        t = _load()
        with tempfile.TemporaryDirectory() as tmp:
            a = t.new_session(Path(tmp))
            b = t.new_session(Path(tmp))
            self.assertNotEqual(a, b)

    def test_empty_or_invalid_text_writes_nothing(self):
        t = _load()
        with tempfile.TemporaryDirectory() as tmp:
            session = t.new_session(Path(tmp))
            for bad in ("", "   ", 42, None):
                with self.assertRaises(ValueError):
                    t.record_turn(session, user_text=bad, reply="ok",
                                  root=Path(tmp))
                with self.assertRaises(ValueError):
                    t.record_turn(session, user_text="ok", reply=bad,
                                  root=Path(tmp))
            self.assertFalse(session.exists())

    def test_invalid_or_unconfined_session_is_rejected(self):
        t = _load()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                t.record_turn(Path("session.jsonl"), user_text="a", reply="b")
            with self.assertRaises(ValueError):
                t.record_turn(Path(tmp) / "missing/session.jsonl",
                              user_text="a", reply="b", root=Path(tmp))
            with self.assertRaises(ValueError):
                t.record_turn(Path(tmp) / "session.txt",
                              user_text="a", reply="b", root=Path(tmp))
            # fuera de la raíz declarada: confinamiento D-10
            with tempfile.TemporaryDirectory() as other:
                outside = Path(other) / "session-x.jsonl"
                outside.touch()
                with self.assertRaises(ValueError):
                    t.record_turn(outside, user_text="a", reply="b",
                                  root=Path(tmp))


class SyntheticSession(unittest.TestCase):
    """Fixture sintético (sin datos personales) contra la raíz real:
    un turno deja el archivo completo y Git lo ignora (D-10). El
    archivo sintético se borra al terminar."""

    def test_synthetic_session_complete_and_ignored_by_git(self):
        t = _load()
        session = t.new_session()
        try:
            self.assertTrue(str(session).startswith(str(PRIVATE)))
            t.record_turn(session, user_text="[fixture] turno sintético",
                          reply="[fixture] respuesta sintética",
                          params={"origin": "test_transcripciones"})
            self.assertEqual(oct(session.stat().st_mode & 0o777), oct(0o600))
            line = json.loads(session.read_text(encoding="utf-8").splitlines()[0])
            self.assertIn("fixture", line["user_text"])
            ignored = subprocess.run(
                ["git", "check-ignore", "-q", str(session)], cwd=str(RAIZ))
            self.assertEqual(ignored.returncode, 0,
                             "la sesión retenida no está ignorada por Git")
            dirty = subprocess.run(
                ["git", "status", "--porcelain"], capture_output=True,
                text=True, cwd=str(RAIZ)).stdout
            self.assertNotIn("privado", dirty,
                             f"la retención ensució Git: {dirty}")
        finally:
            if session.exists():
                session.unlink()


class Wiring(unittest.TestCase):
    """I1-VT cablea la retención en los ejemplos con texto nativo por
    turno; los flujos realtime lo declaran pendiente (sin retención)."""

    def test_examples_with_native_text_retain_turns(self):
        for path in ("examples/wsl/live_voice.py",
                     "examples/conversacion_voz_local.py"):
            source = (RAIZ / path).read_text(encoding="utf-8")
            self.assertIn("record_turn", source, f"{path} sin retención")
            self.assertIn("new_session", source, f"{path} sin sesión D-10")

    def test_realtime_flows_declare_d10_pending(self):
        for path in ("examples/wsl/continuous_unlimited.py",
                     "examples/wsl/continuous_english.py",
                     "examples/wsl/realtime_english.py"):
            source = (RAIZ / path).read_text(encoding="utf-8")
            self.assertNotIn("record_turn", source,
                             f"{path}: retención sin captura de texto real")
            self.assertIn("D-10", source,
                          f"{path} debe declarar D-10 pendiente")


if __name__ == "__main__":
    unittest.main()
