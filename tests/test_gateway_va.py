"""Pruebas I1-VA — transcripción vía input_audio en el gateway
(SPEC-i1-va). Todo rechazo ocurre ANTES del motor: el contador del
backend falso queda en cero."""

import base64
import importlib.util
import json
import struct
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

try:  # funciona con -m tests.test_gateway_va y con discover -s tests
    from tests.test_gateway_i1 import GatewayBase  # noqa: E402
except ImportError:
    from test_gateway_i1 import GatewayBase  # noqa: E402

SPEC_VA = json.loads((RAIZ / "tests/corpus_va.json").read_text())


def wav_prueba(muestras=b"\x00" * 32000, rate=16000, channels=1,
               bits=16, formato=1, extra_final=b""):
    """WAV PCM mínimo bien formado (1 s de silencio por defecto)."""
    bloque = struct.pack(
        "<HHIIHH", formato, channels, rate,
        rate * channels * bits // 8, channels * bits // 8, bits)
    return (b"RIFF" + struct.pack("<I", 36 + len(muestras)) + b"WAVEfmt "
            + struct.pack("<I", 16) + bloque
            + b"data" + struct.pack("<I", len(muestras)) + muestras
            + extra_final)


def parte_audio(datos, formato="wav"):
    return {"type": "input_audio",
            "input_audio": {"data": base64.b64encode(datos).decode(),
                            "format": formato}}


def mensaje_audio(datos, formato="wav"):
    return {"messages": [{"role": "user", "content": [
        parte_audio(datos, formato),
        {"type": "text", "text": "Transcribe."}]}]}


class EntradaValida(GatewayBase):
    def test_va1_audio_valido_atraviesa_y_llega_al_motor(self):
        estado, cuerpo = self.post(mensaje_audio(wav_prueba()))
        self.assertEqual(estado, 200, cuerpo)
        self.assertEqual(self.contador(), 1)
        # el corpus declarado existe y sus hashes calzan
        for item in SPEC_VA["frases"]:
            ruta = RAIZ / "tests" / item["wav"]
            self.assertTrue(ruta.is_file(), f"falta {item['wav']}")
            import hashlib
            self.assertEqual(
                hashlib.sha256(ruta.read_bytes()).hexdigest(), item["sha256"],
                f"hash de {item['wav']} no reproduce el corpus")


class AudioInvalido(GatewayBase):
    def test_va2_wav_corrupto_o_truncado(self):
        casos = {
            "firma falsa": b"RIFX" + b"\x00" * 40,
            "cabeza corta": b"RIFF",
            "truncado a mitad": wav_prueba()[:30],
            "bytes sobrantes": wav_prueba(extra_final=b"\x00\x01"),
            "fmt no pcm": wav_prueba(formato=3),
            "bits distintos": wav_prueba(bits=8),
            "canales cero": wav_prueba(channels=0),
            "tasa cero": wav_prueba(rate=0),
        }
        for nombre, datos in casos.items():
            with self.subTest(caso=nombre):
                estado, cuerpo = self.post(mensaje_audio(datos))
                self.assertEqual(estado, 400, cuerpo)
                self.assertEqual(cuerpo["error"]["code"], "invalid_audio")
        self.assertEqual(self.contador(), 0)

    def test_va2b_base64_invalido(self):
        estado, cuerpo = self.post({"messages": [{"role": "user", "content": [
            {"type": "input_audio",
             "input_audio": {"data": "!!!no-base64!!!", "format": "wav"}},
            {"type": "text", "text": "x"}]}]})
        self.assertEqual(estado, 400)
        self.assertEqual(cuerpo["error"]["code"], "invalid_audio")
        self.assertEqual(self.contador(), 0)

    def test_va2c_chunks_duplicados_o_tamano_inconsistente(self):
        # H1/M1 de la ronda adversarial: un segundo data (o fmt) crea
        # ambigüedad de duración para el motor; el tamaño RIFF debe
        # calzar con el archivo.
        datos = wav_prueba()
        muestras, fmt_chunk = datos[44:], datos[12:36]
        cab_data = b"data" + struct.pack("<I", len(muestras))

        def riff_valido(cuerpo):
            archivo = b"RIFF\x00\x00\x00\x00WAVE" + cuerpo
            return archivo[:4] + struct.pack("<I", len(archivo) - 8) + archivo[8:]

        casos = {
            "data duplicado": riff_valido(fmt_chunk + cab_data + muestras
                                          + cab_data + muestras),
            "data vacío + data real": riff_valido(
                fmt_chunk + b"data" + struct.pack("<I", 0)
                + cab_data + muestras),
            "fmt duplicado": riff_valido(fmt_chunk + fmt_chunk
                                         + cab_data + muestras),
            "tamaño RIFF falso": datos[:4] + struct.pack("<I", 999) + datos[8:],
        }
        for nombre, mal in casos.items():
            with self.subTest(caso=nombre):
                estado, cuerpo = self.post(mensaje_audio(mal))
                self.assertEqual(estado, 400, cuerpo)
                self.assertEqual(cuerpo["error"]["code"], "invalid_audio")
        self.assertEqual(self.contador(), 0)

    def test_va3_presupuesto_de_bytes_y_duracion(self):
        grande = wav_prueba(muestras=b"\x00" * (4 * 1024 * 1024 + 64))
        estado, cuerpo = self.post(mensaje_audio(grande))
        self.assertEqual(estado, 400, cuerpo)
        self.assertIn("presupuesto", cuerpo["error"]["message"])
        # 61 s a 16 kHz mono 16-bit: ~1.95 MiB (bajo la cota de bytes),
        # la duración es la que debe rechazar
        largo = wav_prueba(muestras=b"\x00" * (61 * 16000 * 2))
        estado, cuerpo = self.post(mensaje_audio(largo))
        self.assertEqual(estado, 400, cuerpo)
        self.assertEqual(cuerpo["error"]["code"], "invalid_audio")
        self.assertEqual(self.contador(), 0)

    def test_va4_formas_no_admitidas(self):
        b64 = base64.b64encode(wav_prueba()).decode()
        casos = {
            "audio_url data:": {"type": "audio_url",
                                "audio_url": {"url": "data:audio/wav;base64," + b64}},
            "audio_url http:": {"type": "audio_url",
                                "audio_url": {"url": "https://ejemplo.invalid/x.wav"}},
            "formato mp3": parte_audio(wav_prueba(), formato="mp3"),
            "clave url extra": {"type": "input_audio",
                                "input_audio": {"data": b64, "format": "wav",
                                                "url": "https://x.invalid"}},
            "input_audio no dict": {"type": "input_audio", "input_audio": b64},
        }
        for nombre, parte in casos.items():
            with self.subTest(caso=nombre):
                estado, cuerpo = self.post({"messages": [
                    {"role": "user", "content": [parte,
                                                 {"type": "text", "text": "x"}]}]})
                self.assertEqual(estado, 400, cuerpo)
                self.assertEqual(self.contador(), 0)

    def test_va5_capabilities_anuncia_transcripcion_sin_lo_demas(self):
        estado, cuerpo = self.get("/v1/capabilities")
        self.assertEqual(estado, 200)
        self.assertIn("audio", cuerpo["entrada"])
        self.assertTrue(cuerpo["transcripcion"])
        for clave in ("streaming", "video"):
            self.assertFalse(cuerpo[clave], f"{clave} no puede anunciarse activo")
        self.assertEqual(self.contador(), 0)


class CerPorUnidad(unittest.TestCase):
    """VA7: la función cer y la normalización del método declarado."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "medir_cer_va", RAIZ / "tests/medir_cer_va.py")
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def test_normaliza_minusculas_sin_puntuacion(self):
        self.assertEqual(self.mod.normalizar("Hola, ¿cómo estás?"),
                         "hola cómo estás")
        self.assertEqual(self.mod.normalizar("  El   libro.  "),
                         "el libro")

    def test_cer_casos_conocidos(self):
        self.assertEqual(self.mod.cer("hola", "hola"), 0.0)
        self.assertAlmostEqual(self.mod.cer("hola", "bola"), 0.25)
        self.assertAlmostEqual(self.mod.cer("hola", "halo"), 2 / 4)
        self.assertEqual(self.mod.cer("", ""), 0.0)

    def test_criterio_pass_declarado_en_corpus(self):
        metodo = SPEC_VA["metodo"]
        self.assertTrue(metodo["umbral_declarado_antes_de_medir"])
        self.assertIn("0.10", metodo["criterio_pass"])


if __name__ == "__main__":
    unittest.main()
