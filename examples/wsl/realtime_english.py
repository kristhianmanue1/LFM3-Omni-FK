"""Prueba autorizada: audio nativo WS en inglés, un turno, sin archivos de audio."""
import array
import base64
import importlib.util
import json
import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def stop(process):
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None:
            stream.close()


def receive(connection):
    def exact(size):
        result = bytearray()
        while len(result) < size:
            part = connection.recv(size - len(result))
            if not part:
                raise EOFError('WebSocket cerrado')
            result.extend(part)
        return bytes(result)
    while True:
        first, second = exact(2)
        length = second & 127
        if length == 126:
            length = struct.unpack('>H', exact(2))[0]
        elif length == 127:
            length = struct.unpack('>Q', exact(8))[0]
        if length > 2 * 1024 * 1024 or second & 128 or not first & 128:
            raise ValueError('frame WebSocket fuera de límites')
        payload = exact(length)
        opcode = first & 15
        if opcode == 8:
            raise EOFError('sesión cerrada por el motor')
        if opcode in (9, 10):
            if length > 125:
                raise ValueError('frame de control demasiado grande')
            if opcode == 9:
                mask = os.urandom(4)
                masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
                connection.sendall(bytes([0x8A, 0x80 | length]) + mask + masked)
            continue
        if opcode != 1:
            raise ValueError(f'frame no textual inesperado: opcode {opcode}')
        event = json.loads(payload)
        if not isinstance(event, dict) or not isinstance(event.get('type'), str):
            raise ValueError('evento inválido')
        if event['type'] == 'error':
            raise RuntimeError('el motor rechazó una operación realtime')
        return event


def main():
    if os.environ.get("LFM3_CONSENTIMIENTO_D09") != "si":
        raise ValueError("D09: requiere LFM3_CONSENTIMIENTO_D09=si para usar dispositivos reales")
    spec = importlib.util.spec_from_file_location('probes', ROOT / 'tests/sondas_multimodal.py')
    probes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probes)
    connection = probes._ws()
    connection.settimeout(30)
    recording = playback = None
    try:
        session = receive(connection)['session']
        input_rate = session['audio']['input']['format']['rate']
        output_rate = session['audio']['output']['format']['rate']
        if input_rate != 16000 or output_rate != 24000:
            raise ValueError('formato PCM inesperado')
        probes._enviar(connection, {'type': 'session.update', 'session': {
            'type': 'realtime', 'output_modalities': ['text', 'audio'],
            'max_output_tokens': 100,
            'instructions': 'Speak only English. Have a friendly spoken conversation. '
             'Answer in one or two short sentences. Do not use tools or execute actions.'}})
        if receive(connection)['type'] != 'session.updated':
            raise ValueError('configuración realtime no confirmada')

        def stream_response(label):
            nonlocal playback
            playback = subprocess.Popen([
                '/usr/bin/pacat', '--playback', '--raw', '--format=s16le',
                '--rate=24000', '--channels=1', '--latency-msec=80'],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            fd = playback.stdin.fileno()
            os.set_blocking(fd, False)
            started, first, total, completed = time.monotonic(), None, 0, False
            try:
                while time.monotonic() - started < 90:
                    event = receive(connection)
                    if event['type'] == 'response.output_audio.delta':
                        audio = base64.b64decode(event['delta'], validate=True)
                        if len(audio) % 2 or total + len(audio) > 30 * 24000 * 2:
                            raise ValueError('audio fuera del límite de treinta segundos')
                        first = first if first is not None else time.monotonic() - started
                        total += len(audio)
                        view = memoryview(audio)
                        while view:
                            if not select.select([], [fd], [], 5)[1]:
                                raise TimeoutError('reproducción bloqueada')
                            try:
                                view = view[os.write(fd, view):]
                            except BlockingIOError:
                                continue
                    elif event['type'] == 'response.done':
                        if event.get('response', {}).get('status') != 'completed':
                            raise RuntimeError('respuesta realtime incompleta')
                        completed = True
                        break
                if not completed or not total:
                    raise ValueError('respuesta sin audio completo')
                playback.stdin.close()
                if playback.wait(timeout=35):
                    raise RuntimeError('falló la reproducción PulseAudio')
                print(f'{label}: primer audio {first:.2f} s; duración {total / 48000:.2f} s.', flush=True)
            finally:
                stop(playback)
                playback = None

        probes._enviar(connection, {'type': 'conversation.item.create', 'item': {
            'type': 'message', 'role': 'user', 'content': [{'type': 'input_text',
            'text': 'Say exactly: After the beep, ask me a short question in English. You have ten seconds.'}]}})
        probes._enviar(connection, {'type': 'response.create'})
        stream_response('Saludo nativo')
        subprocess.run(['/usr/bin/ffplay', '-nodisp', '-autoexit', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'sine=frequency=880:duration=0.2'],
                       check=True, timeout=10)
        print('MICRÓFONO ABIERTO: habla en inglés durante diez segundos.', flush=True)
        recording = subprocess.Popen([
            '/usr/bin/ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
            '-f', 'pulse', '-i', 'RDPSource', '-t', '10', '-ar', '16000',
            '-ac', '1', '-f', 's16le', '-'],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        started, sent, peak = time.monotonic(), 0, 0
        captured = bytearray()
        while sent < 320000 and time.monotonic() - started < 15:
            if not select.select([recording.stdout], [], [], 3)[0]:
                raise TimeoutError('micrófono sin datos')
            chunk = os.read(recording.stdout.fileno(), min(3200, 320000 - sent))
            if not chunk:
                break
            if len(chunk) % 2:
                raise ValueError('PCM de entrada inválido')
            sent += len(chunk)
            samples = array.array('h', chunk)
            peak = max(peak, max(abs(value) for value in samples))
            captured.extend(chunk)
        stop(recording)
        recording = None
        print('MICRÓFONO CERRADO. Respuesta nativa en streaming.', flush=True)
        if peak < 300 or sent < 32000:
            raise ValueError('señal de micrófono insuficiente')
        connection.settimeout(30)
        probes._enviar(connection, {'type': 'input_audio_buffer.append',
                                   'audio': base64.b64encode(captured).decode()})
        captured.clear()
        probes._enviar(connection, {'type': 'input_audio_buffer.commit'})
        probes._enviar(connection, {'type': 'response.create'})
        stream_response('Respuesta a tu voz')
        print('FIN. No se crearon archivos de audio ni transcripciones.', flush=True)
    finally:
        try:
            stop(recording)
        finally:
            try:
                stop(playback)
            finally:
                try:
                    connection.settimeout(1)
                    probes._enviar(connection, {'type': 'response.cancel'})
                except OSError:
                    pass
                finally:
                    connection.close()


if __name__ == '__main__':
    try:
        main()
    except (OSError, EOFError, ValueError, KeyError, IndexError, TypeError,
            RuntimeError, subprocess.SubprocessError) as error:
        print('Prueba interrumpida:', type(error).__name__, str(error)[:200], flush=True)
        sys.exit(1)
