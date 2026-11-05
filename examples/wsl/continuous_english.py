"""Conversación exploratoria local por turnos automáticos; no guarda audio."""
import array
import base64
from collections import deque
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import select
import signal
import subprocess
import sys
import time
import urllib.request
import wave

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('voice', Path(__file__).with_name('realtime_english.py'))
voice = importlib.util.module_from_spec(spec)
spec.loader.exec_module(voice)


def capture_vad(deadline):
    """Máximo 20 s sin voz o 20 s de voz; fin tras 1 s de silencio."""
    process = subprocess.Popen([
        '/usr/bin/ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
        '-f', 'pulse', '-i', 'RDPSource', '-t', '40', '-ar', '16000',
        '-ac', '1', '-f', 's16le', '-'],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    started = time.monotonic()
    pre = deque(maxlen=5)
    pending, captured = bytearray(), bytearray()
    speaking, active, quiet = False, 0, 0
    try:
        while time.monotonic() < min(deadline, started + 40):
            if not select.select([process.stdout], [], [], 3)[0]:
                raise TimeoutError('micrófono sin datos')
            part = os.read(process.stdout.fileno(), 3200 - len(pending))
            if not part:
                break
            pending.extend(part)
            if len(pending) < 3200:
                continue
            frame = bytes(pending)
            pending.clear()
            samples = array.array('h', frame)
            rms = math.sqrt(sum(value * value for value in samples) / len(samples))
            loud = rms > 400
            if not speaking:
                pre.append(frame)
                active = active + 1 if loud else 0
                if active >= 3:
                    speaking = True
                    captured.extend(b''.join(pre))
                    print('Voz detectada.', flush=True)
                elif time.monotonic() - started > 20:
                    return None
            else:
                captured.extend(frame)
                quiet = 0 if loud else quiet + 1
                if quiet >= 10 or len(captured) >= 20 * 32000:
                    return bytes(captured)
        return bytes(captured) if speaking else None
    finally:
        voice.stop(process)


def wants_to_end(pcm):
    """ASR sólo detecta la despedida; el turno nativo recibe audio original."""
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(pcm)
    boundary = 'lfm3-' + os.urandom(12).hex()
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="language"'
            f'\r\n\r\nen\r\n--{boundary}\r\nContent-Disposition: form-data; '
            'name="file"; filename="turn.wav"\r\nContent-Type: audio/wav\r\n\r\n').encode()
    body += buffer.getvalue() + f'\r\n--{boundary}--\r\n'.encode()
    request = urllib.request.Request('http://127.0.0.1:8091/v1/audio/transcriptions',
        data=body, headers={'Content-Type': 'multipart/form-data; boundary=' + boundary})
    with urllib.request.urlopen(request, timeout=20) as response:
        text = json.load(response).get('text')
    if not isinstance(text, str) or len(text) > 4000:
        raise ValueError('transcripción inválida para detectar despedida')
    return bool(re.search(r'\b(goodbye|good bye|stop conversation|end conversation)\b', text.lower()))


def play_response(connection, deadline):
    process = subprocess.Popen([
        '/usr/bin/pacat', '--playback', '--raw', '--format=s16le',
        '--rate=24000', '--channels=1', '--latency-msec=80'],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.set_blocking(process.stdin.fileno(), False)
    started, first, total, done = time.monotonic(), None, 0, False
    try:
        while time.monotonic() < min(deadline, started + 60):
            event = voice.receive(connection)
            if event['type'] == 'response.output_audio.delta':
                audio = base64.b64decode(event['delta'], validate=True)
                if len(audio) % 2 or total + len(audio) > 30 * 48000:
                    raise ValueError('audio fuera de límites')
                first = first if first is not None else time.monotonic() - started
                total += len(audio)
                view = memoryview(audio)
                while view:
                    fd = process.stdin.fileno()
                    if not select.select([], [fd], [], 3)[1]:
                        raise TimeoutError('reproducción bloqueada')
                    try:
                        view = view[os.write(fd, view):]
                    except BlockingIOError:
                        continue
            elif event['type'] == 'response.done':
                if event.get('response', {}).get('status') != 'completed':
                    raise RuntimeError('respuesta incompleta')
                done = True
                break
        if not done or not total:
            raise RuntimeError('no se completó la respuesta de voz')
        process.stdin.close()
        if process.wait(timeout=35):
            raise RuntimeError('falló la reproducción')
        print(f'Primer audio: {first:.2f} s; respuesta: {total / 48000:.2f} s.', flush=True)
    finally:
        voice.stop(process)


def main():
    if os.environ.get("LFM3_CONSENTIMIENTO_D09") != "si":
        raise ValueError("D09: requiere LFM3_CONSENTIMIENTO_D09=si para usar dispositivos reales")
    p = importlib.util.spec_from_file_location('probes', ROOT / 'tests/sondas_multimodal.py')
    probes = importlib.util.module_from_spec(p)
    p.loader.exec_module(probes)
    connection = probes._ws()
    connection.settimeout(20)
    deadline = time.monotonic() + 180
    turns = 0
    try:
        session = voice.receive(connection)['session']
        if session['audio']['input']['format']['rate'] != 16000 \
                or session['audio']['output']['format']['rate'] != 24000:
            raise ValueError('formato PCM inesperado')
        probes._enviar(connection, {'type': 'session.update', 'session': {
            'type': 'realtime', 'output_modalities': ['text', 'audio'],
            'max_output_tokens': 140,
            'instructions': 'Converse only in English. Keep each reply to one or two '
            'short natural sentences. Continue the conversation and ask one short '
            'follow-up question when appropriate. If the user says goodbye, say goodbye '
            'briefly. Never execute actions or use tools.'}})
        if voice.receive(connection)['type'] != 'session.updated':
            raise ValueError('configuración no confirmada')
        probes._enviar(connection, {'type': 'conversation.item.create', 'item': {
            'type': 'message', 'role': 'user', 'content': [{'type': 'input_text',
            'text': 'Greet me and ask what I would like to talk about. Keep it short.'}]}})
        probes._enviar(connection, {'type': 'response.create'})
        play_response(connection, deadline)
        while turns < 6 and time.monotonic() < deadline - 25:
            subprocess.run(['/usr/bin/ffplay', '-nodisp', '-autoexit', '-loglevel', 'error',
                            '-f', 'lavfi', '-i', 'sine=frequency=880:duration=0.12'],
                           check=True, timeout=5)
            print(f'ESCUCHANDO TURNO {turns + 1}: termina con una pausa de un segundo.', flush=True)
            captured = capture_vad(deadline)
            print('MICRÓFONO CERRADO.', flush=True)
            if not captured:
                print('Sin voz durante veinte segundos; sesión terminada.', flush=True)
                break
            end = wants_to_end(captured)
            probes._enviar(connection, {'type': 'input_audio_buffer.append',
                                       'audio': base64.b64encode(captured).decode()})
            captured = None
            probes._enviar(connection, {'type': 'input_audio_buffer.commit'})
            probes._enviar(connection, {'type': 'response.create'})
            play_response(connection, deadline)
            turns += 1
            if end:
                print('Despedida detectada. Sesión terminada.', flush=True)
                break
        print(f'FIN: {turns} turnos. No se guardaron grabaciones ni transcripciones.', flush=True)
    finally:
        try:
            connection.settimeout(1)
            probes._enviar(connection, {'type': 'response.cancel'})
        except OSError:
            pass
        finally:
            connection.close()


def interrupt(signum, frame):
    signal.setitimer(signal.ITIMER_REAL, 0)
    raise KeyboardInterrupt


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGALRM, interrupt)
    signal.setitimer(signal.ITIMER_REAL, 180)
    try:
        main()
    except KeyboardInterrupt:
        print('Conversación detenida; micrófono y reproducción cerrados.', flush=True)
    except (OSError, EOFError, ValueError, KeyError, IndexError, TypeError,
            RuntimeError, subprocess.SubprocessError) as error:
        print('Conversación interrumpida:', type(error).__name__, str(error)[:200], flush=True)
        sys.exit(1)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
