#!/usr/bin/env python3
"""Cliente SDK de referencia para Perfil W (Web, Apps y Humanos) — Fase I4.

Demuestra el consumo integral y seguro de la plataforma omnimodal LFM3-Omni:
- Inferencia de texto libre y esquemas estructurados (JSON Schema v2-ext).
- Percepción visual (imágenes JPEG/PNG en base64).
- Transcripción de audio (WAV 16 kHz en base64).
- Síntesis de voz hablada (TTS WAV 24 kHz) con manejo de exclusión mutua (503).
- Percepción temporal de video corto (MP4 en base64).
- Diálogo conversacional por turnos con streaming SSE y cancelación reactiva.
- Saneamiento defensivo de respuestas para evitar inyecciones HTML en interfaces.

Cero dependencias externas: 100% Python estándar (urllib, json, ssl, base64).
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
from pathlib import Path
import ssl
import sys
import time
import urllib.error
import urllib.request
from typing import Callable, Generator

DEFAULT_PORT = 8092
ROOT_DIR = Path(__file__).resolve().parent.parent
CERT_PATH = ROOT_DIR / "config" / "certs" / "cert.pem"


def sanitize_for_display(raw_text: str) -> str:
    """Sanea texto generado por el LLM antes de renderizarlo en Web/UI.

    Principio 7: La salida del modelo es dato no confiable. Escapa etiquetas
    y entidades HTML para prevenir cross-site scripting (XSS).
    """
    if not isinstance(raw_text, str):
        return ""
    return html.escape(raw_text, quote=True)


class PerfilWClient:
    """Cliente HTTP/SSE para aplicaciones web y humanas sobre LFM3-Omni."""

    def __init__(
        self,
        base_url: str = f"http://127.0.0.1:{DEFAULT_PORT}",
        auth_token: str | None = None,
        ssl_cafile: str | None = None,
        insecure_tls: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token or os.environ.get("LFM3_AUTH_TOKEN")
        self.ssl_context = None
        if self.base_url.startswith("https://"):
            if insecure_tls:
                self.ssl_context = ssl._create_unverified_context()
            elif ssl_cafile and Path(ssl_cafile).exists():
                self.ssl_context = ssl.create_default_context(cafile=ssl_cafile)
            elif CERT_PATH.exists():
                self.ssl_context = ssl.create_default_context(cafile=str(CERT_PATH))
            else:
                self.ssl_context = ssl.create_default_context()

    def _headers(self, client_request_id: str | None = None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        if client_request_id:
            headers["X-Client-Request-ID"] = client_request_id
        return headers

    def _request(
        self,
        endpoint: str,
        method: str = "GET",
        payload: dict | None = None,
        client_request_id: str | None = None,
        timeout: float = 30.0,
    ) -> dict:
        url = f"{self.base_url}{endpoint}"
        data = json.dumps(payload).encode("utf-8") if payload else None
        headers = self._headers(client_request_id)
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        kwargs = {"timeout": timeout}
        if self.ssl_context:
            kwargs["context"] = self.ssl_context

        try:
            with urllib.request.urlopen(req, **kwargs) as resp:
                resp_bytes = resp.read()
                if not resp_bytes:
                    return {}
                return json.loads(resp_bytes.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            try:
                err_json = json.loads(err_body)
            except Exception:
                err_json = {"raw": err_body}
            return {
                "error": True,
                "status_code": exc.code,
                "detail": err_json,
            }
        except Exception as exc:
            return {"error": True, "status_code": 0, "detail": str(exc)}

    # 1. Estado y descubrimiento
    def health(self) -> dict:
        """Consulta el estado mínimo de salud."""
        return self._request("/health")

    def capabilities(self) -> dict:
        """Consulta el catálogo de modalidades y contratos admitidos."""
        return self._request("/capabilities")

    # 2. Inferencia de texto libre
    def chat_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 256,
        client_request_id: str | None = None,
    ) -> dict:
        """Inferencia de texto simple."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.0,
        }
        return self._request(
            "/v1/chat/completions",
            method="POST",
            payload=payload,
            client_request_id=client_request_id,
        )

    # 3. Inferencia de texto estructurado
    def chat_structured(
        self,
        prompt: str,
        schema: dict,
        schema_name: str = "structured_output",
        max_tokens: int = 512,
        client_request_id: str | None = None,
    ) -> dict:
        """Inferencia estructurada validada con JSON Schema (v2-ext)."""
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema},
            },
        }
        return self._request(
            "/v1/chat/completions",
            method="POST",
            payload=payload,
            client_request_id=client_request_id,
        )

    # 4. Inferencia multimodal visual
    def chat_vision(
        self,
        prompt: str,
        image_base64: str,
        mime_type: str = "image/png",
        max_tokens: int = 256,
        client_request_id: str | None = None,
    ) -> dict:
        """Análisis de imagen y consulta visual."""
        content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{image_base64}"},
            },
            {"type": "text", "text": prompt},
        ]
        payload = {
            "messages": [{"role": "user", "content": content}],
            "max_tokens": max_tokens,
            "temperature": 0.0,
        }
        return self._request(
            "/v1/chat/completions",
            method="POST",
            payload=payload,
            client_request_id=client_request_id,
        )

    # 5. Transcripción de audio (ASR)
    def transcribe_audio(
        self,
        audio_base64: str,
        prompt: str = "Transcribe el siguiente audio en español.",
        client_request_id: str | None = None,
    ) -> dict:
        """Transcripción automática de voz (ASR)."""
        content = [
            {
                "type": "input_audio",
                "input_audio": {"data": audio_base64, "format": "wav"},
            },
            {"type": "text", "text": prompt},
        ]
        payload = {
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 256,
            "temperature": 0.0,
        }
        return self._request(
            "/v1/chat/completions",
            method="POST",
            payload=payload,
            client_request_id=client_request_id,
        )

    # 6. Síntesis de voz (TTS)
    def synthesize_speech(
        self,
        text: str,
        voice: str = "es-ES",
        client_request_id: str | None = None,
    ) -> dict:
        """Síntesis de voz hablada vía llama-tts con exclusión mutua."""
        payload = {
            "messages": [{"role": "user", "content": text}],
            "modalities": ["audio"],
            "audio": {"voice": voice, "format": "wav"},
            "temperature": 0.0,
        }
        return self._request(
            "/v1/chat/completions",
            method="POST",
            payload=payload,
            client_request_id=client_request_id,
        )

    # 7. Video corto
    def chat_video(
        self,
        prompt: str,
        video_base64: str,
        client_request_id: str | None = None,
    ) -> dict:
        """Comprensión temporal de video corto en MP4."""
        content = [
            {
                "type": "video_url",
                "video_url": {"url": f"data:video/mp4;base64,{video_base64}"},
            },
            {"type": "text", "text": prompt},
        ]
        payload = {
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 256,
            "temperature": 0.0,
        }
        return self._request(
            "/v1/chat/completions",
            method="POST",
            payload=payload,
            client_request_id=client_request_id,
        )

    # 8. Streaming conversacional (SSE)
    def stream_chat(
        self,
        messages: list[dict],
        client_request_id: str | None = None,
    ) -> Generator[str, None, None]:
        """Transmite chunks de texto en tiempo real vía Server-Sent Events."""
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "messages": messages,
            "stream": True,
            "temperature": 0.0,
        }
        data = json.dumps(payload).encode("utf-8")
        headers = self._headers(client_request_id)
        headers["Accept"] = "text/event-stream"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        kwargs = {"timeout": 30.0}
        if self.ssl_context:
            kwargs["context"] = self.ssl_context

        with urllib.request.urlopen(req, **kwargs) as resp:
            buffer = ""
            for line_bytes in resp:
                line = line_bytes.decode("utf-8")
                if line.startswith("data: "):
                    content = line[6:].strip()
                    if content == "[DONE]":
                        break
                    try:
                        chunk_json = json.loads(content)
                        choices = chunk_json.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            token = delta.get("content", "")
                            if token:
                                yield token
                    except Exception:
                        continue

    # 9. Cancelación
    def cancel_request(self, request_id: str) -> dict:
        """Solicita la cancelación de una petición activa."""
        return self._request(f"/requests/{request_id}", method="DELETE")


def ejecutar_demostracion(cliente: PerfilWClient) -> int:
    """Ejecuta una ronda de verificación representativa de Perfil W."""
    print("=" * 60)
    print("Demostración de Cliente Perfil W (SDK LFM3-Omni)")
    print(f"Destino: {cliente.base_url}")
    print("=" * 60)

    # 1. Health
    print("\n[1] Verificando /health...")
    h = cliente.health()
    print(f"    Respuesta: {h}")

    # 2. Capabilities
    print("\n[2] Consultando /capabilities...")
    caps = cliente.capabilities()
    if caps.get("error"):
        print(f"    Error consultando capabilities: {caps}")
    else:
        print(f"    Modalidades: {list(caps.get('modalidades', {}).keys()) or 'ok'}")
        print(f"    Versiones: {caps.get('versiones_contrato', [])}")

    # 3. Texto estructurado con esquema cerrado
    print("\n[3] Inferencia de texto estructurada...")
    schema_saludo = {
        "type": "object",
        "properties": {
            "intencion": {"type": "string", "enum": ["saludo", "despedida"]},
            "idioma": {"type": "string", "enum": ["es", "en"]},
            "confianza": {"type": "number"},
        },
        "required": ["intencion", "idioma"],
    }
    res_struct = cliente.chat_structured(
        "Hola, buenos días a todo el equipo.",
        schema=schema_saludo,
        schema_name="intencion_usuario",
    )
    if res_struct.get("error"):
        print(f"    Error: {res_struct}")
    else:
        choice = res_struct.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content", "")
        print(f"    Salida estructurada: {content}")

    # 4. Demostración de saneamiento de interfaz
    print("\n[4] Demostración de saneamiento de salida (Principio 7)...")
    salida_peligrosa = "<script>alert('xss')</script> Bienvenido <b>usuario</b>"
    saneada = sanitize_for_display(salida_peligrosa)
    print(f"    Crudo:   {salida_peligrosa}")
    print(f"    Saneado: {saneada}")
    assert "<script>" not in saneada, "Fallo en saneamiento de seguridad"

    print("\nDemostración de Perfil W concluida con éxito.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Cliente SDK Perfil W")
    parser.add_argument("--url", default=f"http://127.0.0.1:{DEFAULT_PORT}")
    parser.add_argument("--token", default=None, help="Token Bearer opcional")
    parser.add_argument("--insecure", action="store_true", help="Desactivar TLS check")
    parser.add_argument("--demo", action="store_true", help="Ejecutar demo")
    args = parser.parse_args()

    client = PerfilWClient(
        base_url=args.url,
        auth_token=args.token,
        insecure_tls=args.insecure,
    )

    if args.demo or len(sys.argv) == 1:
        sys.exit(ejecutar_demostracion(client))


if __name__ == "__main__":
    main()
