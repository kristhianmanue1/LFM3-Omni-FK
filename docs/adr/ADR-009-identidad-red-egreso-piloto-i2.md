# ADR-009: Identidad, red, contención de egreso y supervisión para el piloto privado I2

```text
ADR-009: Arquitectura de seguridad, autenticación por proyecto,
topología de red TLS, contención de egreso y supervisión para el
piloto privado por invitación de la Fase I2
Estado: aceptado (propuesto y ratificado en TAREA I2-D, PLAN LFM3-2)
Contexto:
  - Las fases I0, I1 e I1-V completaron y verificaron la superficie
    local de inferencia omnimodal (texto, visión, audio, voz, video,
    schema v2-ext, MCP v2 stdio, CLI y perfil D) en entorno loopback
    estricto (127.0.0.1:8091 y 127.0.0.1:8092).
  - La Fase I2 establece el servicio compartido multi-inquilino para dos
    proyectos invitados (proyecto-alpha y proyecto-beta), lo que introduce
    cuatro requisitos de seguridad no presentes en loopback uniusuario:
    1) Autenticación e identidad por proyecto (S-03, S-10): distinguir
       consumidores, aislar datos, evitar suplantación y revocar accesos
       sin reiniciar el motor de inferencia.
    2) Topología de red y transporte seguro TLS (D-03): proteger el canal
       de comunicación contra intercepción y preservar la regla de oro:
       el motor llama-server (8091) jamás se expone fuera de loopback.
    3) Contención de egreso (anti-SSRF, S-04): impedir que entradas
       multimodales maliciosas induzcan peticiones salientes desde el host
       o el motor hacia recursos de red ajenos.
    4) Supervisión, observabilidad y operación (S-07, S-08): control de
       vida del proceso, rotación de logs sin filtración de secretos ni
       prompts, y evaluación rigurosa con doble experimento de carga.
Decisión:
  1. Identidad, autenticación y cuotas por proyecto:
     - Autenticación mediante tokens Bearer opacos (32..64 caracteres)
       transmitidos en la cabecera `Authorization: Bearer <token>` y
       correlacionados obligatoriamente con `X-Project-ID`.
     - Registro de credenciales en archivo local seguro `config/tokens.json`
       con permisos de sistema `0600`, conteniendo los digests SHA-256 de
       los tokens, scopes autorizados (`infer:text`, `infer:vision`,
       `infer:audio`, `speech:synthesize`, `profile:d`) y parámetros de
       cuota (token bucket, tamaño máximo de cola y timeout).
     - La recarga de tokens revocados o modificados se ejecuta en memoria
       detectando mtime o vía señal de control, sin interrumpir inferencias
       en vuelo de otros proyectos.
  2. Topología de red y terminación TLS:
     - El servicio expone externamente un único puerto seguro (8443)
       mediante terminación TLS (TLS 1.3 / TLS 1.2 estricto) implementada
       en Python stdlib 3.12+ (`ssl.SSLContext`), sin dependencias ajenas.
     - El terminador TLS provee el canal cifrado y reenvía las peticiones
       hacia el gateway interno en `127.0.0.1:8092`, el cual realiza la
       autenticación por token, validación de frontera y control de cuotas.
     - Certificado local fijado con SAN `localhost` / `lfm3.local` y huella
       SHA-256 documentada; se prohíbe el uso de flags inseguras (`-k`).
     - El puerto `8091` del motor `llama-server` permanece cerrado a todo
       tráfico que no provenga de `127.0.0.1`.
  3. Contención estricta de egreso (Zero Egress y anti-SSRF):
     - Allowlist positiva estricta: todo medio debe suministrarse como
       `data:<mime>;base64,...`. Se deniega cualquier esquema URI (`http://`,
       `https://`, `ftp://`, `file://`, etc.) con 400 `invalid_payload`.
     - Los procesos del motor y utilidades (`llama-server`, `llama-tts`,
       `ffmpeg`) se ejecutan sin permisos de acceso a red saliente mediante
       sandbox del sistema operativo.
     - Criterio fail-closed: si el mecanismo de sandbox a nivel OS resulta
       inviable o no verificable en el host sin alterar el cortafuegos
       global, el servicio mantiene bloqueada la exposición remota.
     - El mantenimiento administrativo (Hugging Face, Homebrew) se realiza
       manualmente en ventanas programadas fuera de la inferencia activa.
  4. Supervisión y observabilidad sin fuga de datos:
     - El supervisor de procesos garantiza arranque determinista, reinicio
       ante caídas accidentales con backoff (evitando bucles infinitos) y
       parada limpia (`run/stop.sh`).
     - Los logs de auditoría registran exclusivamente metadatos operativos:
       `timestamp`, `request_id`, `project_id`, `endpoint`, `status_code`,
       `duration_ms`, `tokens_prompt`, `tokens_generated`.
     - Se prohíbe terminantemente registrar en logs el contenido del prompt,
       imágenes, audio, texto generado o tokens de autenticación.
  5. Doble evaluación de carga (D-04):
     - Experimento A: Medición end-to-end con la configuración real del
       piloto y carga de 1, 2, 4 y 8 clientes, verificando tasa de
       admisión real, tiempo de cola (p50/p95) y rechazo 429/503.
     - Experimento B: Medición aislada del motor para conocer su techo
       físico en condiciones térmicas controladas, sin atribuir sus cifras
       al rendimiento ofrecido a los proyectos piloto.
Alternativas descartadas:
  - Servidor OAuth2 / OpenID Connect completo (Keycloak / Auth0):
    Introduce dependencias pesadas de red y servicios externos, violando
    el Principio 1 (simplicidad) y la regla de no dependencias externas.
  - Proxy inverso externo compilado (Nginx / Caddy):
    Requiere empaquetado y dependencias externas ausentes en el entorno base;
    el terminador TLS en Python stdlib satisface la necesidad con cero deps.
  - Exposición directa de llama-server con Basic Auth:
    Inseguro, no proporciona cuotas por proyecto, carece de validación
    multimodal en frontera y vulnera el Principio 7 y S-03.
  - Permitir descarga de imágenes o audio desde URLs remotas en gateway:
    Abre vectores críticos de SSRF y denegación de servicio por recursos
    lentos o maliciosos.
Consecuencias:
  - Gana: Arquitectura robusta, aislada y lista para producción privada,
    cumpliendo cabalmente con S-03, S-04, S-07, S-08 y S-10.
  - Pierde: Los clientes remotos deben enviar medios como base64 data URI
    y gestionar cabeceras Bearer y X-Project-ID.
```
