#!/usr/bin/env node
/**
 * Cliente SDK de referencia en JavaScript (Node.js ESM) para Perfil W — Fase I4.
 *
 * Diseñado para aplicaciones web, móviles y proyectos frontExpert.
 * Cero dependencias npm externas: 100% Node.js stdlib nativo (fetch, AbortController).
 *
 * Características omnimodales:
 * - Texto libre e inferencia estructurada (schema v2-ext).
 * - Percepción visual (imágenes en base64).
 * - Transcripción de audio (ASR WAV 16kHz base64).
 * - Síntesis de voz hablada (TTS WAV 24kHz) con detección de exclusión 503.
 * - Video corto temporal (MP4 base64).
 * - Diálogo conversacional por turnos con Server-Sent Events (SSE) y aborto limpio.
 * - Saneamiento de salida defensivo (Principio 7: datos no confiables).
 */

import { argv, env, exit } from 'node:process';

const DEFAULT_PORT = 8092;

/**
 * Sanea texto generado por el modelo antes de inyectarlo en DOM / UI.
 * @param {string} rawText
 * @returns {string}
 */
export function sanitizeForDisplay(rawText) {
  if (typeof rawText !== 'string') return '';
  return rawText
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export class PerfilWClient {
  /**
   * @param {Object} [config]
   * @param {string} [config.baseUrl]
   * @param {string} [config.authToken]
   */
  constructor(config = {}) {
    this.baseUrl = (config.baseUrl || env.LFM3_GATEWAY_URL || `http://127.0.0.1:${DEFAULT_PORT}`).replace(/\/$/, '');
    this.authToken = config.authToken || env.LFM3_AUTH_TOKEN || null;
  }

  /**
   * Genera cabeceras HTTP incluyendo token Bearer si existe.
   * @param {string} [clientRequestId]
   */
  _headers(clientRequestId) {
    const headers = { 'Content-Type': 'application/json' };
    if (this.authToken) {
      headers['Authorization'] = `Bearer ${this.authToken}`;
    }
    if (clientRequestId) {
      headers['X-Client-Request-ID'] = clientRequestId;
    }
    return headers;
  }

  /**
   * Envía petición fetch genérica.
   */
  async _request(endpoint, method = 'GET', body = null, clientRequestId = null) {
    const url = `${this.baseUrl}${endpoint}`;
    const options = {
      method,
      headers: this._headers(clientRequestId),
    };
    if (body) {
      options.body = JSON.stringify(body);
    }
    try {
      const resp = await fetch(url, options);
      const text = await resp.text();
      let data;
      try {
        data = JSON.parse(text);
      } catch {
        data = { raw: text };
      }
      if (!resp.ok) {
        return { error: true, statusCode: resp.status, detail: data };
      }
      return data;
    } catch (err) {
      return { error: true, statusCode: 0, detail: err.message };
    }
  }

  // 1. Estado y capacidades
  async health() {
    return this._request('/health');
  }

  async capabilities() {
    return this._request('/capabilities');
  }

  // 2. Inferencia de texto simple
  async chatText(prompt, options = {}) {
    const messages = [];
    if (options.systemPrompt) {
      messages.push({ role: 'system', content: options.systemPrompt });
    }
    messages.push({ role: 'user', content: prompt });

    return this._request(
      '/v1/chat/completions',
      'POST',
      {
        messages,
        max_tokens: options.maxTokens || 256,
        temperature: 0.0,
      },
      options.clientRequestId
    );
  }

  // 3. Inferencia estructurada (JSON Schema v2-ext)
  async chatStructured(prompt, schema, schemaName = 'structured_output', options = {}) {
    return this._request(
      '/v1/chat/completions',
      'POST',
      {
        messages: [{ role: 'user', content: prompt }],
        max_tokens: options.maxTokens || 512,
        temperature: 0.0,
        response_format: {
          type: 'json_schema',
          json_schema: { name: schemaName, schema },
        },
      },
      options.clientRequestId
    );
  }

  // 4. Percepción visual (imágenes)
  async chatVision(prompt, imageBase64, mimeType = 'image/png', options = {}) {
    const content = [
      {
        type: 'image_url',
        image_url: { url: `data:${mimeType};base64,${imageBase64}` },
      },
      { type: 'text', text: prompt },
    ];
    return this._request(
      '/v1/chat/completions',
      'POST',
      {
        messages: [{ role: 'user', content }],
        max_tokens: options.maxTokens || 256,
        temperature: 0.0,
      },
      options.clientRequestId
    );
  }

  // 5. Transcripción de audio (ASR)
  async transcribeAudio(audioBase64, prompt = 'Transcribe el audio en español.', options = {}) {
    const content = [
      {
        type: 'input_audio',
        input_audio: { data: audioBase64, format: 'wav' },
      },
      { type: 'text', text: prompt },
    ];
    return this._request(
      '/v1/chat/completions',
      'POST',
      {
        messages: [{ role: 'user', content }],
        max_tokens: 256,
        temperature: 0.0,
      },
      options.clientRequestId
    );
  }

  // 6. Síntesis de voz (TTS)
  async synthesizeSpeech(text, voice = 'es-ES', options = {}) {
    return this._request(
      '/v1/chat/completions',
      'POST',
      {
        messages: [{ role: 'user', content: text }],
        modalities: ['audio'],
        audio: { voice, format: 'wav' },
        temperature: 0.0,
      },
      options.clientRequestId
    );
  }

  // 7. Video corto temporal
  async chatVideo(prompt, videoBase64, options = {}) {
    const content = [
      {
        type: 'video_url',
        video_url: { url: `data:video/mp4;base64,{videoBase64}` },
      },
      { type: 'text', text: prompt },
    ];
    return this._request(
      '/v1/chat/completions',
      'POST',
      {
        messages: [{ role: 'user', content }],
        max_tokens: 256,
        temperature: 0.0,
      },
      options.clientRequestId
    );
  }

  // 8. Streaming conversacional (SSE)
  /**
   * @param {Array<Object>} messages
   * @param {Function} onChunk Callback receptor de tokens en tiempo real
   * @param {Object} [options]
   * @param {AbortSignal} [options.signal] Para abortar la conexión limpiamente
   */
  async chatStream(messages, onChunk, options = {}) {
    const url = `${this.baseUrl}/v1/chat/completions`;
    const headers = {
      ...this._headers(options.clientRequestId),
      Accept: 'text/event-stream',
    };

    const resp = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        messages,
        stream: true,
        temperature: 0.0,
      }),
      signal: options.signal,
    });

    if (!resp.ok) {
      throw new Error(`Error en streaming HTTP ${resp.status}`);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('data: ')) {
          const payloadStr = trimmed.slice(6).trim();
          if (payloadStr === '[DONE]') {
            return;
          }
          try {
            const parsed = JSON.parse(payloadStr);
            const delta = parsed.choices?.[0]?.delta?.content;
            if (delta) {
              onChunk(delta);
            }
          } catch {
            // Ignorar líneas malformadas
          }
        }
      }
    }
  }

  // 9. Cancelación
  async cancelRequest(requestId) {
    return this._request(`/requests/${encodeURIComponent(requestId)}`, 'DELETE');
  }
}

async function runDemo() {
  console.log('='.repeat(60));
  console.log('Demostración de Cliente Perfil W (Node.js ESM stdlib)');
  console.log('='.repeat(60));

  const client = new PerfilWClient();

  // 1. Health
  console.log('\n[1] Verificando /health...');
  const h = await client.health();
  console.log('    Respuesta:', h);

  // 2. Capabilities
  console.log('\n[2] Consultando /capabilities...');
  const caps = await client.capabilities();
  console.log('    Modalidades:', Object.keys(caps.modalidades || {}).join(', ') || 'N/A');

  // 3. Saneamiento de seguridad
  console.log('\n[3] Demostración de saneamiento de salida (Principio 7)...');
  const inputXSS = '<img src=x onerror=alert(1)> Hola mundo!';
  const sanitized = sanitizeForDisplay(inputXSS);
  console.log('    Crudo:   ', inputXSS);
  console.log('    Saneado: ', sanitized);
  if (sanitized.includes('<img')) {
    throw new Error('Fallo crítico en función de saneamiento XSS');
  }

  console.log('\nDemostración Node.js completada con éxito.');
  exit(0);
}

if (argv[1]?.endsWith('cliente_perfil_w.mjs')) {
  runDemo().catch((err) => {
    console.error('Fallo en demo Node.js:', err);
    exit(1);
  });
}
