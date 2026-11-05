"""Sesión local autorizada sin límite total; termina con goodbye o SIGTERM.

D-10 pendiente: este flujo realtime aún no expone texto de turno, así que
no retiene transcripciones (I1-VT cubre live_voice/conversacion_voz_local);
no usarlo como sesión auditable hasta cablearlo.
"""
import array
import base64
from collections import deque
import importlib.util
import math
import os
from pathlib import Path
import queue
import select
import signal
import socket
import subprocess
import sys
import threading
import time

spec = importlib.util.spec_from_file_location('previous', Path(__file__).with_name('continuous_english.py'))
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
voice = previous.voice


class Session:
    def __init__(self):
        spec = importlib.util.spec_from_file_location(
            'probes', previous.ROOT / 'tests/sondas_multimodal.py')
        self.probes = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.probes)
        self.socket = self.probes._ws()
        self.socket.settimeout(60)
        self.lock = threading.RLock()
        self.events = queue.Queue(maxsize=64)
        self.failure = None
        self.closed = threading.Event()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def recv(self, size):
        return self.socket.recv(size)

    def sendall(self, data):
        with self.lock:
            self.socket.sendall(data)

    def send(self, event):
        self.check()
        self.probes._enviar(self, event)

    def _read(self):
        try:
            while not self.closed.is_set():
                event = voice.receive(self)
                self.events.put(event, timeout=3)
        except (OSError, EOFError, ValueError, KeyError, TypeError,
                RuntimeError, queue.Full) as error:
            if not self.closed.is_set():
                self.failure = error

    def check(self):
        if self.failure is not None:
            raise RuntimeError('la sesión realtime perdió la conexión') from self.failure

    def next(self):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            self.check()
            try:
                return self.events.get(timeout=1)
            except queue.Empty:
                continue
        raise TimeoutError('el motor no envió una respuesta')

    def close(self):
        self.closed.set()
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.socket.close()
        self.reader.join(timeout=4)


def listen(session):
    process = subprocess.Popen([
        '/usr/bin/ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
        '-f', 'pulse', '-i', 'RDPSource', '-ar', '16000', '-ac', '1',
        '-f', 's16le', '-'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    pending, captured = bytearray(), bytearray()
    pre = deque(maxlen=5)
    speaking, active, quiet = False, 0, 0
    try:
        while True:
            session.check()
            if not select.select([process.stdout], [], [], 3)[0]:
                raise TimeoutError('micrófono sin datos')
            part = os.read(process.stdout.fileno(), 3200 - len(pending))
            if not part:
                raise EOFError('el micrófono se cerró')
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
            else:
                captured.extend(frame)
                quiet = 0 if loud else quiet + 1
                if quiet >= 10 or len(captured) >= 20 * 32000:
                    return bytes(captured)
    finally:
        voice.stop(process)


def play(session):
    process = subprocess.Popen([
        '/usr/bin/pacat', '--playback', '--raw', '--format=s16le',
        '--rate=24000', '--channels=1', '--latency-msec=80'],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.set_blocking(process.stdin.fileno(), False)
    started, first, total, done = time.monotonic(), None, 0, False
    try:
        while time.monotonic() - started < 90:
            event = session.next()
            if event['type'] == 'response.output_audio.delta':
                audio = base64.b64decode(event['delta'], validate=True)
                if len(audio) % 2 or total + len(audio) > 30 * 48000:
                    raise ValueError('audio fuera de límites por respuesta')
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
            raise RuntimeError('respuesta de voz no completada')
        process.stdin.close()
        if process.wait(timeout=35):
            raise RuntimeError('falló la reproducción')
        print(f'Primer audio {first:.2f} s; voz {total / 48000:.2f} s.', flush=True)
    finally:
        voice.stop(process)


def main():
    if os.environ.get("LFM3_CONSENTIMIENTO_D09") != "si":
        raise ValueError("D09: requiere LFM3_CONSENTIMIENTO_D09=si para usar dispositivos reales")
    session = Session()
    turns = 0
    try:
        created = session.next()['session']
        if created['audio']['input']['format']['rate'] != 16000 \
                or created['audio']['output']['format']['rate'] != 24000:
            raise ValueError('formato PCM inesperado')
        session.send({'type': 'session.update', 'session': {
            'type': 'realtime', 'output_modalities': ['text', 'audio'],
            'max_output_tokens': 140,
            'instructions': 'Converse only in English. Keep replies to one or two '
            'short natural sentences. Maintain the conversation and ask follow-up '
            'questions. If I say goodbye, say goodbye briefly. Never execute actions '
            'or use tools.'}})
        if session.next()['type'] != 'session.updated':
            raise ValueError('configuración no confirmada')
        session.send({'type': 'conversation.item.create', 'item': {'type': 'message',
            'role': 'user', 'content': [{'type': 'input_text',
            'text': 'Greet me briefly and ask what I would like to talk about.'}]}})
        session.send({'type': 'response.create'})
        play(session)
        while True:
            subprocess.run(['/usr/bin/ffplay', '-nodisp', '-autoexit', '-loglevel', 'error',
                            '-f', 'lavfi', '-i', 'sine=frequency=880:duration=0.12'],
                           check=True, timeout=5)
            print(f'ESCUCHANDO TURNO {turns + 1}. Di goodbye para terminar.', flush=True)
            captured = listen(session)
            print('MICRÓFONO CERRADO. Procesando turno.', flush=True)
            end = previous.wants_to_end(captured)
            session.send({'type': 'input_audio_buffer.append',
                          'audio': base64.b64encode(captured).decode()})
            captured = None
            session.send({'type': 'input_audio_buffer.commit'})
            session.send({'type': 'response.create'})
            play(session)
            turns += 1
            if end:
                print('GOODBYE detectado. Cerrando sesión.', flush=True)
                break
        print(f'FIN: {turns} turnos. Sin grabaciones ni transcripciones guardadas.', flush=True)
    finally:
        session.close()


def interrupt(signum, frame):
    raise KeyboardInterrupt


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, interrupt)
    try:
        main()
    except KeyboardInterrupt:
        print('Sesión detenida; micrófono y reproducción cerrados.', flush=True)
    except (OSError, EOFError, ValueError, KeyError, IndexError, TypeError,
            RuntimeError, subprocess.SubprocessError) as error:
        print('Sesión interrumpida:', type(error).__name__, str(error)[:200], flush=True)
        sys.exit(1)
