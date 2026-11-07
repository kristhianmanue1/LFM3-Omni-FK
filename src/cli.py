#!/usr/bin/env python3
"""CLI unificado stdlib para LFM3-Omni (SPEC-i1-vc §1, ADR-008).

Permite interactuar con el gateway loopback local (127.0.0.1:8092)
en todas las modalidades activas: salud, texto, visión, audio, voz y video.
Sin dependencias externas.

Uso:
  python3 src/cli.py health [--json]
  python3 src/cli.py text <prompt | - > [--schema ARCHIVO] [--max-tokens N] [--json]
  python3 src/cli.py vision --image RUTA <prompt> [--schema ARCHIVO] [--json]
  python3 src/cli.py audio --audio RUTA <prompt> [--schema ARCHIVO] [--json]
  python3 src/cli.py speech <input | - > [--output RUTA] [--voice V] [--speed S]
  python3 src/cli.py video --video RUTA <prompt> [--schema ARCHIVO] [--json]
"""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _gateway_url():
    if "LFM3_GATEWAY_URL" in os.environ:
        return os.environ["LFM3_GATEWAY_URL"].rstrip("/")
    host = os.environ.get("LFM3_GATEWAY_HOST", "127.0.0.1")
    port = int(os.environ.get("LFM3_GATEWAY_PORT", "8092"))
    return f"http://{host}:{port}"


def _extraer_mensaje_error(cuerpo):
    if isinstance(cuerpo, dict):
        err = cuerpo.get("error")
        if isinstance(err, dict):
            return err.get("message", str(cuerpo))
        if isinstance(err, str):
            return err
        return str(cuerpo)
    return cuerpo.decode("utf-8", errors="replace") if hasattr(cuerpo, "decode") else str(cuerpo)


def _peticion_http(metodo, ruta, payload=None, timeout=120, crudo=False):
    url = f"{_gateway_url()}{ruta}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            bytes_resp = resp.read()
            if crudo:
                return resp.status, bytes_resp
            try:
                return resp.status, json.loads(bytes_resp.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                sys.stderr.write(f"Error parseando JSON de respuesta ({url}): {exc}\n")
                sys.exit(1)
    except urllib.error.HTTPError as exc:
        cuerpo = exc.read()
        try:
            detalle = json.loads(cuerpo.decode("utf-8"))
        except Exception:
            detalle = {"error": {"message": str(cuerpo)}}
        return exc.code, detalle
    except (urllib.error.URLError, OSError) as exc:
        sys.stderr.write(f"Error de conexión con el gateway ({url}): {exc}\n")
        sys.exit(1)


def _cargar_schema(param):
    if not param:
        return None
    try:
        p = Path(param)
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception as exc:
                sys.stderr.write(f"Error al leer schema desde archivo '{param}': {exc}\n")
                sys.exit(1)
    except OSError:
        pass
    try:
        return json.loads(param)
    except Exception as exc:
        sys.stderr.write(f"Error al parsear schema como JSON string: {exc}\n")
        sys.exit(1)


def _leer_archivo_o_b64(param, extensiones_validas=None):
    try:
        p = Path(param)
        if p.is_file():
            raw = p.read_bytes()
            return base64.b64encode(raw).decode("ascii"), raw
    except OSError:
        pass
    # Intentar decodificar como base64 directo
    try:
        raw = base64.b64decode(param, validate=True)
        return param, raw
    except Exception:
        sys.stderr.write(f"Parámetro no es archivo accesible ni base64 válido: {param[:30]}...\n")
        sys.exit(1)


def _leer_texto(prompt_arg):
    if prompt_arg == "-":
        return sys.stdin.read().strip()
    return prompt_arg


def comando_health(args):
    st_h, c_h = _peticion_http("GET", "/healthz", timeout=5)
    st_c, c_c = _peticion_http("GET", "/v1/capabilities", timeout=5)
    resultado = {
        "status": "ok" if st_h == 200 else "down",
        "gateway_url": _gateway_url(),
        "capabilities": c_c if st_c == 200 else {},
    }
    if args.json:
        print(json.dumps(resultado, indent=2, ensure_ascii=False))
    else:
        estado = "UP" if st_h == 200 else "DOWN"
        print(f"LFM3-Omni Gateway: {estado} en {_gateway_url()}")
        if st_c == 200:
            print(f"  Entrada: {c_c.get('entrada', [])}")
            print(f"  Salida:  {c_c.get('salida', [])}")
            print(f"  Streaming: {c_c.get('streaming')}, Video: {c_c.get('video')}")
    sys.exit(0 if st_h == 200 else 1)


def comando_text(args):
    prompt = _leer_texto(args.prompt)
    if not prompt:
        sys.stderr.write("Error: prompt no puede estar vacío\n")
        sys.exit(1)
    schema = _cargar_schema(args.schema)
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": args.max_tokens,
        "temperature": args.temperature,
    }
    if schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "salida", "schema": schema},
        }
    status, cuerpo = _peticion_http("POST", "/v1/chat/completions", payload)
    if status != 200:
        err = _extraer_mensaje_error(cuerpo)
        sys.stderr.write(f"Error {status}: {err}\n")
        sys.exit(1)
    if args.json:
        print(json.dumps(cuerpo, indent=2, ensure_ascii=False))
    else:
        texto = cuerpo["choices"][0]["message"]["content"]
        print(texto)


def comando_vision(args):
    prompt = _leer_texto(args.prompt)
    b64, raw = _leer_archivo_o_b64(args.image)
    mime = "image/png" if raw.startswith(b"\x89PNG") else "image/jpeg"
    schema = _cargar_schema(args.schema)
    payload = {
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                {"type": "text", "text": prompt},
            ],
        }],
        "max_tokens": args.max_tokens,
    }
    if schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "salida", "schema": schema},
        }
    status, cuerpo = _peticion_http("POST", "/v1/chat/completions", payload)
    if status != 200:
        err = _extraer_mensaje_error(cuerpo)
        sys.stderr.write(f"Error {status}: {err}\n")
        sys.exit(1)
    if args.json:
        print(json.dumps(cuerpo, indent=2, ensure_ascii=False))
    else:
        print(cuerpo["choices"][0]["message"]["content"])


def comando_audio(args):
    prompt = _leer_texto(args.prompt)
    b64, raw = _leer_archivo_o_b64(args.audio)
    schema = _cargar_schema(args.schema)
    payload = {
        "messages": [{
            "role": "user",
            "content": [
                {"type": "input_audio", "input_audio": {"data": b64, "format": "wav"}},
                {"type": "text", "text": prompt},
            ],
        }],
        "max_tokens": args.max_tokens,
    }
    if schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "salida", "schema": schema},
        }
    status, cuerpo = _peticion_http("POST", "/v1/chat/completions", payload)
    if status != 200:
        err = _extraer_mensaje_error(cuerpo)
        sys.stderr.write(f"Error {status}: {err}\n")
        sys.exit(1)
    if args.json:
        print(json.dumps(cuerpo, indent=2, ensure_ascii=False))
    else:
        print(cuerpo["choices"][0]["message"]["content"])


def comando_speech(args):
    texto = _leer_texto(args.input)
    if not texto:
        sys.stderr.write("Error: input de voz no puede estar vacío\n")
        sys.exit(1)
    payload = {
        "input": texto,
        "language": "es",
        "response_format": "wav",
    }
    status, cuerpo = _peticion_http("POST", "/v1/audio/speech", payload, timeout=60, crudo=True)
    if status == 503:
        sys.stderr.write("Error 503: Motor de voz ocupado (reintentable)\n")
        sys.exit(1)
    if status != 200:
        err = _extraer_mensaje_error(cuerpo)
        sys.stderr.write(f"Error {status}: {err}\n")
        sys.exit(1)
    if args.output:
        try:
            Path(args.output).write_bytes(cuerpo)
        except OSError as exc:
            sys.stderr.write(f"Error escribiendo archivo '{args.output}': {exc}\n")
            sys.exit(1)
        if not args.quiet:
            print(f"Audio sintetizado guardado en: {args.output} ({len(cuerpo)} bytes)")
    elif not sys.stdout.isatty():
        sys.stdout.buffer.write(cuerpo)
        sys.stdout.flush()
    else:
        out_defecto = "salida.wav"
        try:
            Path(out_defecto).write_bytes(cuerpo)
        except OSError as exc:
            sys.stderr.write(f"Error escribiendo archivo '{out_defecto}': {exc}\n")
            sys.exit(1)
        print(f"Audio guardado por defecto en: {out_defecto} ({len(cuerpo)} bytes)")


def comando_video(args):
    prompt = _leer_texto(args.prompt)
    b64, raw = _leer_archivo_o_b64(args.video)
    schema = _cargar_schema(args.schema)
    payload = {
        "messages": [{
            "role": "user",
            "content": [
                {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{b64}"}},
                {"type": "text", "text": prompt},
            ],
        }],
        "max_tokens": args.max_tokens,
    }
    if schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "salida", "schema": schema},
        }
    status, cuerpo = _peticion_http("POST", "/v1/chat/completions", payload)
    if status != 200:
        err = _extraer_mensaje_error(cuerpo)
        sys.stderr.write(f"Error {status}: {err}\n")
        sys.exit(1)
    if args.json:
        print(json.dumps(cuerpo, indent=2, ensure_ascii=False))
    else:
        print(cuerpo["choices"][0]["message"]["content"])


def main():
    parser = argparse.ArgumentParser(
        description="CLI unificado stdlib para LFM3-Omni",
        prog="lfm3-cli",
    )
    sub = parser.add_subparsers(dest="subcomando", required=True)

    # health
    p_health = sub.add_parser("health", help="Estado y capacidades del gateway")
    p_health.add_argument("--json", action="store_true", help="Salida JSON")
    p_health.set_defaults(func=comando_health)

    # text
    p_text = sub.add_parser("text", help="Inferencia de texto")
    p_text.add_argument("prompt", help="Prompt de entrada (o '-' para stdin)")
    p_text.add_argument("--schema", help="Archivo o JSON de esquema de salida")
    p_text.add_argument("--max-tokens", type=int, default=512)
    p_text.add_argument("--temperature", type=float, default=0.0)
    p_text.add_argument("--json", action="store_true", help="Salida JSON")
    p_text.set_defaults(func=comando_text)

    # vision
    p_vis = sub.add_parser("vision", help="Inferencia sobre imagen")
    p_vis.add_argument("--image", required=True, help="Ruta o base64 de imagen PNG/JPEG")
    p_vis.add_argument("prompt", help="Pregunta o instrucción (o '-' para stdin)")
    p_vis.add_argument("--schema", help="Archivo o JSON de esquema de salida")
    p_vis.add_argument("--max-tokens", type=int, default=1024)
    p_vis.add_argument("--json", action="store_true", help="Salida JSON")
    p_vis.set_defaults(func=comando_vision)

    # audio
    p_aud = sub.add_parser("audio", help="Inferencia sobre audio WAV")
    p_aud.add_argument("--audio", required=True, help="Ruta o base64 de audio WAV")
    p_aud.add_argument("prompt", help="Instrucción de transcripción/análisis")
    p_aud.add_argument("--schema", help="Archivo o JSON de esquema de salida")
    p_aud.add_argument("--max-tokens", type=int, default=1024)
    p_aud.add_argument("--json", action="store_true", help="Salida JSON")
    p_aud.set_defaults(func=comando_audio)

    # speech
    p_sp = sub.add_parser("speech", help="Síntesis de voz en español")
    p_sp.add_argument("input", help="Texto para sintetizar (o '-' para stdin)")
    p_sp.add_argument("--output", help="Ruta de archivo WAV destino")
    p_sp.add_argument("--voice", default="es_ES-davefx-medium")
    p_sp.add_argument("--speed", type=float, default=1.0)
    p_sp.add_argument("--quiet", action="store_true", help="Sin avisos en stderr")
    p_sp.set_defaults(func=comando_speech)

    # video
    p_vid = sub.add_parser("video", help="Inferencia sobre video MP4")
    p_vid.add_argument("--video", required=True, help="Ruta o base64 de video MP4")
    p_vid.add_argument("prompt", help="Instrucción sobre el video")
    p_vid.add_argument("--schema", help="Archivo o JSON de esquema de salida")
    p_vid.add_argument("--max-tokens", type=int, default=1024)
    p_vid.add_argument("--json", action="store_true", help="Salida JSON")
    p_vid.set_defaults(func=comando_video)

    parsed = parser.parse_args()
    parsed.func(parsed)


if __name__ == "__main__":
    main()
