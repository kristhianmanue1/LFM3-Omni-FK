"""Pruebas I1-VS — síntesis de voz vía llama-tts en el gateway (SPEC-i1-vs).

Verifica en frontera:
- VS1: POST /v1/audio/speech válido entrega audio/wav, pasa el prompt por
  archivo 0600 con -f (jamás en argv) y borra temporales al terminar.
- VS2: input vacío, >600 chars, con caracteres de control, tipos inválidos,
  claves extra (voice, speaker_ref) o language/response_format distintos ->
  400 antes de invocar llama-tts (contador TTS = 0).
- VS3: exclusión mutua sin cola -> segunda petición simultánea recibe 503
  overloaded.
- VS4: fallo de subproceso o salida no-WAV -> 502 backend_error y limpieza.
- VS5: capabilities anuncia voz/audio y salida ["texto", "audio"], sin
  streaming ni video.
"""

import json
import os
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import gateway_http  # noqa: E402
try:
    from tests.test_gateway_i1 import GatewayBase  # noqa: E402
except ImportError:
    from test_gateway_i1 import GatewayBase  # noqa: E402


def _wav_falso(muestras=b"\x00\x00" * 8000, rate=24000):
    bloque = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
    return (b"RIFF" + struct.pack("<I", 36 + len(muestras)) + b"WAVEfmt "
            + struct.pack("<I", 16) + bloque
            + b"data" + struct.pack("<I", len(muestras)) + muestras)


class SpeechBase(GatewayBase):
    def setUp(self):
        super().setUp()
        self.tts_calls = []
        self.tts_delay = 0.0
        self.tts_fail = False
        self.tts_timeout = False
        self.tts_bad_wav = False
        self.tts_empty_wav = False

        def runner_falso(argv, prompt_path, wav_path, env):
            # Invariante ADR-007: el prompt existe con modo 0600 y su texto
            # NO viaja en argv.
            st = os.stat(prompt_path)
            modo = stat.S_IMODE(st.st_mode)
            texto = Path(prompt_path).read_text(encoding="utf-8")
            self.tts_calls.append({
                "argv": list(argv),
                "prompt_path": str(prompt_path),
                "wav_path": str(wav_path),
                "modo": modo,
                "texto": texto,
                "env": dict(env),
            })
            if self.tts_delay:
                time.sleep(self.tts_delay)
            if self.tts_timeout:
                raise subprocess.TimeoutExpired(cmd=argv, timeout=120)
            if self.tts_fail:
                raise OSError("fallo simulado de llama-tts")
            if self.tts_empty_wav:
                Path(wav_path).write_bytes(_wav_falso(muestras=b""))
            else:
                Path(wav_path).write_bytes(
                    b"corrupto" if self.tts_bad_wav else _wav_falso()
                )

        self.gateway.tts_runner = runner_falso

    def post_speech(self, payload, crudo=None, cabeceras=None):
        data = crudo if crudo is not None else json.dumps(payload).encode()
        cab = {"Content-Type": "application/json"}
        cab.update(cabeceras or {})
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/audio/speech",
            data=data, headers=cab)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read()), dict(exc.headers)


class SintesisValida(SpeechBase):
    def test_vs1_speech_valido_entrega_wav_por_archivo_0600_y_limpia(self):
        frase = "Hola, esta es una prueba de síntesis local."
        estado, cuerpo, headers = self.post_speech({"input": frase})
        self.assertEqual(estado, 200, cuerpo)
        self.assertEqual(headers.get("Content-Type"), "audio/wav")
        self.assertTrue(cuerpo.startswith(b"RIFF") and cuerpo[8:12] == b"WAVE")
        self.assertEqual(len(self.tts_calls), 1)
        llamada = self.tts_calls[0]
        self.assertEqual(llamada["modo"], 0o600)
        self.assertEqual(llamada["texto"], frase)
        # El texto jamás aparece en argv (ADR-007)
        for arg in llamada["argv"]:
            self.assertNotIn("prueba de síntesis", arg)
        self.assertIn("-f", llamada["argv"])
        # Archivos temporales eliminados antes de responder
        self.assertFalse(os.path.exists(llamada["prompt_path"]))
        self.assertFalse(os.path.exists(llamada["wav_path"]))
        self.assertEqual(self.contador(), 0)


class RechazosFronteraSpeech(SpeechBase):
    def test_vs2_entradas_invalidas_rechazadas_con_contador_cero(self):
        casos = {
            "sin input": {},
            "input vacio": {"input": ""},
            "input solo espacios": {"input": "   "},
            "input no string": {"input": 123},
            "input con newline": {"input": "Hola\nmundo"},
            "input con nulo": {"input": "Hola\x00mundo"},
            "input con tab": {"input": "Hola\tmundo"},
            "input > 600 chars": {"input": "a" * 601},
            "clave extra voice": {"input": "Hola", "voice": "alloy"},
            "clave extra speaker_ref": {"input": "Hola", "speaker_ref": "/tmp/x"},
            "idioma no soportado": {"input": "Hola", "language": "en"},
            "formato no soportado": {"input": "Hola", "response_format": "mp3"},
            "model no string": {"input": "Hola", "model": 42},
        }
        for nombre, payload in casos.items():
            with self.subTest(caso=nombre):
                estado, cuerpo, _ = self.post_speech(payload)
                self.assertEqual(estado, 400, f"{nombre}: {cuerpo}")
                self.assertIn("error", cuerpo)
                self.assertIn("request_id", cuerpo["error"])
        self.assertEqual(len(self.tts_calls), 0)
        self.assertEqual(self.contador(), 0)


class ExclusionMutuaYErrores(SpeechBase):
    def test_vs3_ocupado_responde_503_overloaded_sin_cola(self):
        self.tts_delay = 0.35
        resultados = [None, None]
        barrera = threading.Event()

        def primero():
            barrera.set()
            resultados[0] = self.post_speech({"input": "Primera frase."})

        hilo = threading.Thread(target=primero)
        hilo.start()
        barrera.wait(timeout=2)
        time.sleep(0.08)
        resultados[1] = self.post_speech({"input": "Segunda simultánea."})
        hilo.join(timeout=5)

        self.assertEqual(resultados[0][0], 200)
        self.assertEqual(resultados[1][0], 503)
        self.assertEqual(resultados[1][1]["error"]["code"], "overloaded")
        self.assertEqual(len(self.tts_calls), 1)

    def test_vs4_fallo_subproceso_o_wav_corrupto_da_502_y_limpia(self):
        self.tts_fail = True
        estado, cuerpo, _ = self.post_speech({"input": "Hola."})
        self.assertEqual(estado, 502)
        self.assertEqual(cuerpo["error"]["code"], "backend_error")
        self.assertFalse(os.path.exists(self.tts_calls[-1]["prompt_path"]))

        # TimeoutExpired del subproceso -> 502 controlado
        self.tts_fail = False
        self.tts_timeout = True
        estado_to, cuerpo_to, _ = self.post_speech({"input": "Hola."})
        self.assertEqual(estado_to, 502)
        self.assertEqual(cuerpo_to["error"]["code"], "backend_error")
        self.assertFalse(os.path.exists(self.tts_calls[-1]["prompt_path"]))

        # WAV corrupto -> 502 invalid_tts_output
        self.tts_timeout = False
        self.tts_bad_wav = True
        estado2, cuerpo2, _ = self.post_speech({"input": "Hola."})
        self.assertEqual(estado2, 502)
        self.assertEqual(cuerpo2["error"]["code"], "backend_error")
        self.assertFalse(os.path.exists(self.tts_calls[-1]["wav_path"]))

        # WAV de 44 bytes con data(0) sin muestras -> 502 invalid_tts_output
        self.tts_bad_wav = False
        self.tts_empty_wav = True
        estado3, cuerpo3, _ = self.post_speech({"input": "Hola."})
        self.assertEqual(estado3, 502)
        self.assertEqual(cuerpo3["error"]["code"], "backend_error")
        self.assertEqual(cuerpo3["error"]["detail"], "invalid_tts_output")

        # OSError al crear directorio temporal (ej. ENOSPC) -> 502 controlado
        self.tts_empty_wav = False
        with mock.patch.object(
                tempfile, "mkdtemp", side_effect=OSError("ENOSPC simulado")):
            estado4, cuerpo4, _ = self.post_speech({"input": "Hola."})
        self.assertEqual(estado4, 502)
        self.assertEqual(cuerpo4["error"]["code"], "backend_error")
        self.assertFalse(gateway_http.LOCK_TTS.locked())

    def test_vs4b_resolver_entorno_tts_verifica_hash_y_limpia_env(self):
        with mock.patch.dict(os.environ, {"LLAMA_ARG_TEMP": "99"}):
            bin_tts, modelo, mmproj, env = gateway_http._resolver_entorno_tts()
        self.assertTrue(os.path.isfile(bin_tts))
        self.assertTrue(os.path.isfile(modelo))
        self.assertTrue(os.path.isfile(mmproj))
        self.assertNotIn("LLAMA_ARG_TEMP", env)
        with mock.patch.object(
                gateway_http, "_sha256_archivo", return_value="0" * 64):
            with self.assertRaises(OSError):
                gateway_http._resolver_entorno_tts()


class CapabilitiesSpeech(SpeechBase):
    def test_vs5_capabilities_anuncia_voz_y_audio_salida(self):
        estado, cuerpo = self.get("/v1/capabilities")
        self.assertEqual(estado, 200)
        self.assertEqual(cuerpo["entrada"], ["texto", "imagen", "audio", "video"])
        self.assertEqual(cuerpo["salida"], ["texto", "audio"])
        self.assertTrue(cuerpo["transcripcion"])
        self.assertTrue(cuerpo["voz"])
        self.assertTrue(cuerpo["audio"])
        self.assertTrue(cuerpo["video"])


if __name__ == "__main__":
    unittest.main()
