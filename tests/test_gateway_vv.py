"""Pruebas I1-VV — video corto en el gateway (SPEC-i1-vv).

Todo rechazo ocurre ANTES del motor: el contador del backend falso queda
en cero.
"""

import base64
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import gateway_http  # noqa: E402
from gateway_core import CAPABILITIES  # noqa: E402

try:
    from tests.test_gateway_i1 import GatewayBase  # noqa: E402
except ImportError:
    from test_gateway_i1 import GatewayBase  # noqa: E402

SPEC_VV = json.loads((RAIZ / "tests/corpus_vv.json").read_text())


def _mp4_minimo_valido(duracion=2, fps=8, ancho=160, alto=120):
    """Genera un MP4 mínimo sintético con ffmpeg para pruebas unitarias."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
        ruta = tf.name
    try:
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi",
            "-i", f"color=c=red:s={ancho}x{alto}:d={duracion},format=yuv420p",
            "-r", str(fps), ruta,
        ], check=True)
        return Path(ruta).read_bytes()
    finally:
        os.unlink(ruta)


def parte_video(datos, formato="video/mp4"):
    b64 = base64.b64encode(datos).decode("ascii")
    return {
        "type": "video_url",
        "video_url": {"url": f"data:{formato};base64,{b64}"},
    }


def mensaje_video(datos, pregunta="Describe el video."):
    return {
        "messages": [{
            "role": "user",
            "content": [
                parte_video(datos),
                {"type": "text", "text": pregunta},
            ],
        }]
    }


class VideoValido(GatewayBase):
    def test_vv1_video_valido_atraviesa_y_llega_al_motor(self):
        datos = _mp4_minimo_valido(duracion=2, fps=8)
        estado, cuerpo = self.post(mensaje_video(datos))
        self.assertEqual(estado, 200, cuerpo)
        self.assertEqual(self.contador(), 1)
        # Los fixtures del corpus existen y reproducen sus hashes
        for caso in SPEC_VV["casos"]:
            ruta = RAIZ / "tests" / caso["archivo"]
            self.assertTrue(ruta.is_file(), f"falta {caso['archivo']}")
            import hashlib
            self.assertEqual(
                hashlib.sha256(ruta.read_bytes()).hexdigest(),
                caso["sha256"],
                f"hash de {caso['archivo']} no reproduce el corpus",
            )


class VideoInvalido(GatewayBase):
    def test_vv2_mp4_corrupto_truncado_o_sin_ftyp(self):
        casos = {
            "cabeza corta": b"RIFF1234WAVE",
            "sin ftyp": b"\x00\x00\x00\x18mdat" + b"\x00" * 30,
            "truncado": b"\x00\x00\x00\x18ftypisom"[:10],
            "basura aleatoria": b"abcdefghijklmnop" * 10,
        }
        for nombre, datos in casos.items():
            with self.subTest(caso=nombre):
                estado, cuerpo = self.post(mensaje_video(datos))
                self.assertEqual(estado, 400, cuerpo)
                self.assertEqual(cuerpo["error"]["code"], "invalid_video")
        self.assertEqual(self.contador(), 0)

    def test_vv2b_base64_invalido(self):
        estado, cuerpo = self.post({
            "messages": [{
                "role": "user",
                "content": [{
                    "type": "video_url",
                    "video_url": {"url": "data:video/mp4;base64,!!!no_b64!!!"},
                }],
            }]
        })
        self.assertEqual(estado, 400)
        self.assertEqual(cuerpo["error"]["code"], "invalid_video")
        self.assertEqual(self.contador(), 0)

    def test_vv3_presupuesto_duracion_fps_y_frames(self):
        # 1. Bytes > 16 MiB rechazados de inmediato
        grande = b"\x00\x00\x00\x18ftypisom" + b"\x00" * (16 * 1024 * 1024 + 64)
        estado, cuerpo = self.post(mensaje_video(grande))
        self.assertEqual(estado, 400)
        self.assertEqual(cuerpo["error"]["code"], "invalid_video")
        self.assertIn("presupuesto", cuerpo["error"]["message"])

        # 2. Duración > 10 s rechazada
        largo = _mp4_minimo_valido(duracion=12, fps=8)
        estado2, cuerpo2 = self.post(mensaje_video(largo))
        self.assertEqual(estado2, 400)
        self.assertEqual(cuerpo2["error"]["code"], "invalid_video")
        self.assertIn("duración", cuerpo2["error"]["message"])

        # 3. FPS > 30 rechazado
        rapido = _mp4_minimo_valido(duracion=2, fps=60)
        estado3, cuerpo3 = self.post(mensaje_video(rapido))
        self.assertEqual(estado3, 400)
        self.assertEqual(cuerpo3["error"]["code"], "invalid_video")
        self.assertIn("FPS", cuerpo3["error"]["message"])

        # 4. Frames > 120 rechazado (ej. 7s a 20 fps = 140 frames)
        muchos_frames = _mp4_minimo_valido(duracion=7, fps=20)
        estado4, cuerpo4 = self.post(mensaje_video(muchos_frames))
        self.assertEqual(estado4, 400)
        self.assertEqual(cuerpo4["error"]["code"], "invalid_video")
        self.assertIn("frames", cuerpo4["error"]["message"])

        # 5. Resolución > 1080p rechazada (ej. 2000x1200 > 1920x1080)
        alta_res = _mp4_minimo_valido(duracion=1, fps=5, ancho=2000, alto=1200)
        estado5, cuerpo5 = self.post(mensaje_video(alta_res))
        self.assertEqual(estado5, 400)
        self.assertEqual(cuerpo5["error"]["code"], "invalid_video")
        self.assertIn("resolución", cuerpo5["error"]["message"])

        self.assertEqual(self.contador(), 0)

    def test_vv4_formas_no_admitidas_y_urls_externas(self):
        datos = _mp4_minimo_valido(duracion=1, fps=8)
        b64 = base64.b64encode(datos).decode("ascii")
        casos = {
            "url http": {
                "type": "video_url",
                "video_url": {"url": "https://ejemplo.invalid/v.mp4"},
            },
            "url file": {
                "type": "video_url",
                "video_url": {"url": "file:///tmp/v.mp4"},
            },
            "formato webm": {
                "type": "video_url",
                "video_url": {"url": f"data:video/webm;base64,{b64}"},
            },
            "clave extra detail": {
                "type": "video_url",
                "video_url": {
                    "url": f"data:video/mp4;base64,{b64}",
                    "detail": "high",
                },
            },
            "video_url no dict": {
                "type": "video_url",
                "video_url": f"data:video/mp4;base64,{b64}",
            },
        }
        for nombre, parte in casos.items():
            with self.subTest(caso=nombre):
                estado, cuerpo = self.post({
                    "messages": [{
                        "role": "user",
                        "content": [parte, {"type": "text", "text": "x"}],
                    }]
                })
                self.assertEqual(estado, 400, f"{nombre}: {cuerpo}")
                self.assertIn(
                    cuerpo["error"]["code"],
                    ("unknown_content_type", "external_url_rejected",
                     "invalid_video"),
                )
        self.assertEqual(self.contador(), 0)

    def test_vv5_ffprobe_alterado_o_ausente_falla_502(self):
        datos = _mp4_minimo_valido(duracion=1, fps=8)
        with mock.patch.object(
            gateway_http, "_resolver_ffprobe",
            side_effect=OSError("hash ffprobe alterado"),
        ):
            estado, cuerpo = self.post(mensaje_video(datos))
            self.assertEqual(estado, 502)
            self.assertEqual(cuerpo["error"]["code"], "backend_error")
            self.assertEqual(cuerpo["error"]["detail"], "ffmpeg_hash_mismatch")
        self.assertEqual(self.contador(), 0)

    def test_vv5b_ffprobe_timeout_o_error_responde_400(self):
        datos = _mp4_minimo_valido(duracion=1, fps=8)
        with mock.patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ffprobe", timeout=15),
        ):
            estado, cuerpo = self.post(mensaje_video(datos))
            self.assertEqual(estado, 400)
            self.assertEqual(cuerpo["error"]["code"], "invalid_video")
            self.assertIn("tiempo límite", cuerpo["error"]["message"])
        self.assertEqual(self.contador(), 0)


class CapabilitiesVideo(GatewayBase):
    def test_vv6_capabilities_anuncia_video_y_todas_las_modalidades(self):
        estado, cuerpo = self.get("/v1/capabilities")
        self.assertEqual(estado, 200)
        self.assertIn("video", cuerpo["entrada"])
        self.assertTrue(cuerpo["video"])
        self.assertTrue(cuerpo["transcripcion"])
        self.assertTrue(cuerpo["voz"])
        self.assertTrue(cuerpo["streaming"])
        self.assertTrue(cuerpo["audio"])
        self.assertEqual(self.contador(), 0)


if __name__ == "__main__":
    unittest.main()
