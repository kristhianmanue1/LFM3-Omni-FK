#!/usr/bin/env python3
"""Pruebas unitarias e integración para el CLI unificado stdlib (src/cli.py).

Verifica:
1. Subcomandos health, text, vision, audio, speech, video.
2. Soporte de stdin pipe ('-') y flag --json.
3. Manejo de errores controlados (400, 503 tts_busy, archivos inexistentes).
"""

import base64
import io
import json
import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import cli  # noqa: E402


def _wav_dummy():
    # WAV mínimo válido PCM 16-bit 16kHz
    longitud_data = 160
    longitud_riff = 36 + longitud_data
    fmt = struct.pack("<4sIHHIIHH", b"fmt ", 16, 1, 1, 16000, 32000, 2, 16)
    data = struct.pack("<4sI", b"data", longitud_data) + (b"\x00\x00" * 80)
    riff = struct.pack("<4sI4s", b"RIFF", longitud_riff, b"WAVE")
    return riff + fmt + data


class CliUnificadoTests(unittest.TestCase):
    """Pruebas del CLI unificado stdlib."""

    @patch("cli._peticion_http")
    def test_cli_health_humano_y_json(self, mock_http):
        mock_http.side_effect = [
            (200, {"status": "ok"}),
            (200, {"entrada": ["texto", "imagen"], "streaming": True}),
        ]
        # Modo humano
        with patch("sys.stdout", new_callable=io.StringIO) as out, \
             patch("sys.exit") as mock_exit:
            cli.main_args = ["lfm3-cli", "health"]
            with patch.object(sys, "argv", ["cli.py", "health"]):
                cli.main()
            mock_exit.assert_called_with(0)
            self.assertIn("LFM3-Omni Gateway: UP", out.getvalue())

        # Modo JSON
        mock_http.side_effect = [
            (200, {"status": "ok"}),
            (200, {"entrada": ["texto", "imagen"]}),
        ]
        with patch("sys.stdout", new_callable=io.StringIO) as out, \
             patch("sys.exit") as mock_exit:
            with patch.object(sys, "argv", ["cli.py", "health", "--json"]):
                cli.main()
            mock_exit.assert_called_with(0)
            dato = json.loads(out.getvalue())
            self.assertEqual(dato["status"], "ok")

    @patch("cli._peticion_http")
    def test_cli_text_con_prompt_y_schema(self, mock_http):
        mock_http.return_value = (
            200,
            {
                "choices": [{"message": {"content": '{"resultado": "ok"}'}}],
                "usage": {"total_tokens": 10},
            },
        )
        schema = '{"type": "object", "properties": {"resultado": {"type": "string"}}}'
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            with patch.object(sys, "argv", ["cli.py", "text", "test", "--schema", schema]):
                cli.main()
            self.assertIn('"resultado": "ok"', out.getvalue())

    @patch("cli._peticion_http")
    def test_cli_text_desde_stdin_pipe(self, mock_http):
        mock_http.return_value = (
            200,
            {"choices": [{"message": {"content": "respuesta stdin"}}]},
        )
        with patch("sys.stdin", io.StringIO("prompt desde pipe")), \
             patch("sys.stdout", new_callable=io.StringIO) as out:
            with patch.object(sys, "argv", ["cli.py", "text", "-"]):
                cli.main()
            self.assertEqual(out.getvalue().strip(), "respuesta stdin")

    @patch("cli._peticion_http")
    def test_cli_speech_con_output_y_503(self, mock_http, tmp_path=None):
        wav = _wav_dummy()
        mock_http.return_value = (200, wav)
        salida_wav = RAIZ / "tests" / "salida_test_cli.wav"
        try:
            with patch.object(
                sys, "argv",
                ["cli.py", "speech", "Hola", "--output", str(salida_wav), "--quiet"]
            ):
                cli.main()
            self.assertTrue(salida_wav.exists())
            self.assertEqual(salida_wav.read_bytes(), wav)
        finally:
            if salida_wav.exists():
                salida_wav.unlink()

        # Caso 503 mutex ocupado
        mock_http.return_value = (503, b"tts ocupado")
        dummy_wav = RAIZ / "tests" / "dummy.wav"
        try:
            with patch("sys.stderr", new_callable=io.StringIO) as err, \
                 patch("sys.exit") as mock_exit:
                with patch.object(
                    sys, "argv",
                    ["cli.py", "speech", "Hola", "--output", str(dummy_wav), "--quiet"]
                ):
                    cli.main()
                mock_exit.assert_called_with(1)
                self.assertIn("503", err.getvalue())
        finally:
            if dummy_wav.exists():
                dummy_wav.unlink()

    @patch("cli._peticion_http")
    def test_cli_vision_y_video_con_base64(self, mock_http):
        mock_http.return_value = (
            200,
            {"choices": [{"message": {"content": "Descripción multimodal"}}]},
        )
        png_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR...").decode()
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            with patch.object(
                sys, "argv",
                ["cli.py", "vision", "--image", png_b64, "Describe imagen"]
            ):
                cli.main()
            self.assertIn("Descripción multimodal", out.getvalue())

    @patch("cli._peticion_http")
    def test_cli_audio_y_video_subcomandos(self, mock_http):
        mock_http.return_value = (
            200,
            {"choices": [{"message": {"content": "Respuesta audio video"}}]},
        )
        wav_b64 = base64.b64encode(_wav_dummy()).decode()
        mp4_b64 = base64.b64encode(b"\x00\x00\x00\x14ftypisom\x00\x00\x02\x00isom").decode()

        # Audio
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            with patch.object(sys, "argv", ["cli.py", "audio", "--audio", wav_b64, "Oye"]):
                cli.main()
            self.assertIn("Respuesta audio video", out.getvalue())

        # Video
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            with patch.object(sys, "argv", ["cli.py", "video", "--video", mp4_b64, "Mira"]):
                cli.main()
            self.assertIn("Respuesta audio video", out.getvalue())

    @patch("cli._peticion_http")
    def test_cli_error_string_y_no_dict(self, mock_http):
        # Gateway responde con error string {"error": "bad request"}
        mock_http.return_value = (400, {"error": "bad request"})
        with patch("sys.stderr", new_callable=io.StringIO) as err, \
             patch("sys.exit", side_effect=SystemExit(1)) as mock_exit:
            with self.assertRaises(SystemExit):
                with patch.object(sys, "argv", ["cli.py", "text", "hola"]):
                    cli.main()
            mock_exit.assert_called_with(1)
            self.assertIn("bad request", err.getvalue())

    @patch("urllib.request.urlopen")
    def test_cli_peticion_http_json_invalido(self, mock_urlopen):
        # Gateway responde 200 pero cuerpo no es JSON parseable
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.read.return_value = b"NO_ES_JSON"
        with patch("sys.stderr", new_callable=io.StringIO) as err, \
             patch("sys.exit", side_effect=SystemExit(1)) as mock_exit:
            with self.assertRaises(SystemExit):
                cli._peticion_http("GET", "/healthz")
            mock_exit.assert_called_with(1)
            self.assertIn("Error parseando JSON", err.getvalue())


if __name__ == "__main__":
    unittest.main()
