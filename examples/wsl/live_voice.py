"""Prueba exploratoria local de un turno, autorizada en esta conversación.

Captura PulseAudio durante 10 s, ASR local, respuesta local y TTS español.
No conserva audio, prompts ni transcripciones en disco al terminar.
"""
import array
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
import wave

ROOT = Path(__file__).resolve().parents[2]
BASE = 'http://127.0.0.1:8091'


def request(path, payload, content_type='application/json'):
    raw = json.dumps(payload).encode() if isinstance(payload, dict) else payload
    req = urllib.request.Request(BASE + path, data=raw,
                                 headers={'Content-Type': content_type})
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.load(response)


def main():
    if os.environ.get("LFM3_CONSENTIMIENTO_D09") != "si":
        raise ValueError("D09: requiere LFM3_CONSENTIMIENTO_D09=si para usar dispositivos reales")
    os.umask(0o077)
    spec = importlib.util.spec_from_file_location('wsl', ROOT / 'scripts/install_wsl.py')
    wsl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wsl)
    runtime = wsl.BASE / 'runtime'
    env = wsl.runtime_env(runtime)
    tts = wsl.executable(runtime, 'llama-tts')
    model = wsl.BASE / 'cache/LFM3-Omni-2B-Q4_K_M.gguf'
    projector = wsl.BASE / 'cache/mmproj-LFM3-Omni-2B-Q4_0.gguf'

    with tempfile.TemporaryDirectory(prefix='lfm3-live-voice-') as directory:
        folder = Path(directory)

        def synthesize(text, name):
            if not isinstance(text, str):
                raise ValueError('respuesta de texto inválida')
            text = ''.join(c for c in text if c.isprintable()).strip()[:600]
            if not text:
                raise ValueError('respuesta vacía')
            prompt, output = folder / (name + '.txt'), folder / (name + '.wav')
            prompt.write_text(text, encoding='utf-8')
            completed = subprocess.run(
                [str(tts), '-m', str(model), '-mm', str(projector),
                 '--tts-lang', 'es', '-f', str(prompt), '-o', str(output)],
                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=90)
            if completed.returncode or not output.is_file():
                raise RuntimeError('falló la síntesis local de voz')
            return output

        def play(path):
            subprocess.run(['/usr/bin/ffplay', '-nodisp', '-autoexit',
                            '-loglevel', 'error', str(path)],
                           check=True, timeout=60)

        greeting = synthesize('Vamos a probar el micrófono. Después del pitido, '
                              'hazme una pregunta corta. Tienes diez segundos.', 'greeting')
        print('SALUDO LISTO. Se reproducirá antes de abrir el micrófono.', flush=True)
        play(greeting)
        beep = folder / 'beep.wav'
        with wave.open(str(beep), 'wb') as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            samples = array.array('h', [int(5000 * math.sin(2 * math.pi * 880 * n / 16000))
                                         for n in range(2400)])
            output.writeframes(samples.tobytes())
        play(beep)
        print('MICRÓFONO ABIERTO: 10 segundos.', flush=True)
        recording = folder / 'input.wav'
        subprocess.run(['/usr/bin/ffmpeg', '-hide_banner', '-loglevel', 'error',
                        '-nostdin', '-f', 'pulse', '-i', 'RDPSource', '-t', '10',
                        '-ar', '16000', '-ac', '1', str(recording)],
                       check=True, timeout=25)
        print('MICRÓFONO CERRADO. Procesando localmente.', flush=True)
        with wave.open(str(recording), 'rb') as source:
            samples = array.array('h', source.readframes(source.getnframes()))
        if not samples or max(abs(s) for s in samples) < 300:
            print('No se detectó señal suficiente. No se solicita transcripción.', flush=True)
            return 2
        boundary = 'lfm3-live-' + os.urandom(12).hex()
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="language"'
                f'\r\n\r\nes\r\n--{boundary}\r\nContent-Disposition: form-data; '
                'name="file"; filename="input.wav"\r\nContent-Type: audio/wav\r\n\r\n').encode()
        body += recording.read_bytes() + f'\r\n--{boundary}--\r\n'.encode()
        transcript = request('/v1/audio/transcriptions', body,
                             'multipart/form-data; boundary=' + boundary).get('text')
        if not isinstance(transcript, str) or not transcript.strip() or len(transcript) > 3000:
            raise ValueError('transcripción vacía o inválida')
        reply = request('/v1/chat/completions', {
            'messages': [
                {'role': 'system', 'content': 'Conversas por voz en español. Responde '
                 'en una o dos frases cortas, sin listas, formato ni emojis. '
                 'Solo conversa; no puedes ejecutar acciones ni comandos.'},
                {'role': 'user', 'content': transcript.strip()}],
            'temperature': 0, 'max_tokens': 100})['choices'][0]['message']['content']
        spoken = synthesize(reply, 'reply')
        print('RESPUESTA LISTA. Reproduciendo voz en español.', flush=True)
        play(spoken)
    print('FIN: archivos temporales eliminados.', flush=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, IndexError, TypeError,
            RuntimeError, subprocess.SubprocessError) as error:
        print('Prueba interrumpida:', type(error).__name__, str(error)[:250], flush=True)
        sys.exit(1)
