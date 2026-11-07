# Dossier de operación del piloto privado HTTPS (Fase I2)

Estado: PROPUESTO para adopción en TAREA I2-D (PLAN LFM3-2).
Procedencia: D-02, D-03, D-04, S-03, S-04, S-07, S-08, S-10; ADR-009, SPEC-i2.
Límite de lectura: documento de referencia operativa fuera de la ruta de lectura.

## 1. Responsables y canales de comunicación

| Rol | Responsable | Suplente / Mecanismo | Canal de escalado |
|---|---|---|---|
| **Operador Principal** | Operador humano | Agente ejecutor bajo encargo explícito | Sesión interactiva de control |
| **Vigilancia Técnica** | Agente de guardia | Procedimiento manual registrado | `docs/reviews/evidence/` |
| **Seguridad y Revocación** | Operador humano | Edición directa en `config/tokens.json` | Ejecución de `run/stop.sh` |

En caso de anomalía operativa, fuga de memoria o saturación sostenida, el
sistema escala localmente mediante registros de alerta en disco sin enviar
tráfico a terceros ni exponer identificadores a internet.

## 2. Proyectos piloto autorizados (D-02)

El piloto privado restringe el acceso a dos proyectos invitados con propósitos
y credenciales diferenciadas:

### 2.1 Proyecto A: `proyecto-alpha`
- **Tipo de consumidor**: Agente autónomo / CLI analítico de medios.
- **Datos permitidos**: Fixtures sintéticos y conjuntos de canarios
  autorizados sin información personal identificable (PII).
- **Modalidades autorizadas**: Texto, visión (imágenes/video corto), audio
  (ASR) y síntesis de voz (TTS).
- **Cuotas asignadas**:
  - Tasa: 60 peticiones por minuto.
  - Ráfaga (*burst*): 5 peticiones.
  - Concurrencia máxima: 1 inferencia en ejecución activa.
  - Cola máxima: 2 peticiones en espera (tiempo máximo en cola: 10.0 s).

### 2.2 Proyecto B: `proyecto-beta`
- **Tipo de consumidor**: Adaptador Perfil D para simulación robótica / UI.
- **Datos permitidos**: Observaciones sintéticas de entorno con timestamps y
  propuestas de acción bajo esquema cerrado.
- **Modalidades autorizadas**: Texto, visión estructurada y Perfil D.
- **Cuotas asignadas**:
  - Tasa: 30 peticiones por minuto.
  - Ráfaga (*burst*): 3 peticiones.
  - Concurrencia máxima: 1 inferencia en ejecución activa.
  - Cola máxima: 2 peticiones en espera (tiempo máximo en cola: 10.0 s,
    sincronizado con el SLO global y protegido por planificación justa).

Se prohíbe de manera estricta el acceso cruzado entre proyectos: las colas,
métricas, logs y cachés se aíslan por `project_id`.

## 3. Infraestructura, red y presupuesto (D-03)

### 3.1 Hardware anfitrión
- **Nodo principal de inferencia**: Apple Silicon M2 con 16 GiB de memoria
  unificada (macOS).
- **Nodo secundario para validación CUDA**: Dell G7 7700 con Intel Core i7 y
  NVIDIA RTX 2070 (8 GiB VRAM, WSL2/Ubuntu).

### 3.2 Presupuesto y cotas de memoria
- **Presupuesto financiero**: $0.00 USD (hardware propio en red privada).
- **Cotas de memoria (RSS)**:
  - Motor `llama-server` (8091): <= 4.0 GiB RSS.
  - Subproceso `llama-tts` (síntesis de voz): <= 4.0 GiB RSS (pico histórico:
    3094.5 MiB).
  - Gateway HTTP, terminador TLS y buffers: <= 512 MiB RSS.
  - Techo máximo de memoria del servicio completo: <= 10.0 GiB RSS (dejando al
    menos 6 GiB libres para el sistema operativo y el Operador).

### 3.3 Red y terminación TLS
- Interfaz externa: puerto `8443` con terminación TLS 1.3 / TLS 1.2 estricto
  vía Python stdlib `ssl.SSLContext`.
- Backend en loopback estricto: `127.0.0.1:8092` (gateway) y `127.0.0.1:8091`
  (motor).
- Contención de egreso: Cero tráfico saliente durante la inferencia. Se deniega
  la descarga de URLs remotas en cualquier payload (`data URI` obligatorio).

## 4. Objetivos de nivel de servicio (SLO) para el piloto (D-04)

Estos umbrales se fijan antes de iniciar cualquier medición en la Fase I2:

1. **Disponibilidad y éxito**:
   - Éxito >= 99.0% de las solicitudes válidas admitidas durante la operación
     normal (excluyendo pruebas con fallos deliberadamente inducidos).
2. **Latencias de respuesta**:
   - TTFT (*Time To First Token*) en texto: p95 <= 5.0 s.
   - Generación completa de texto (64 tokens): p95 <= 30.0 s.
   - Inferencia de visión (imagen + prompt): p95 <= 8.0 s.
   - Síntesis de voz español (TTS): p95 <= 5.0 s.
   - Tiempo de retención en cola: p95 <= 10.0 s.
3. **Manejo de saturación**:
   - Toda solicitud que exceda la tasa debe recibir un rechazo ordenado con
     código `429 Too Many Requests` en menos de 50 ms.
   - Toda solicitud que encuentre la cola llena debe recibir un rechazo
     ordenado con código `503 Service Unavailable` (`overloaded`).
   - El tiempo de desconexión del cliente debe liberar el slot en el motor en
     menos de 500 ms, sin generar slots bloqueados o fantasma.

## 5. Mantenimiento, revocación y rollback

### 5.1 Destinos de mantenimiento autorizados
- `huggingface.co`: verificación periódica de integridad del artefacto GGUF.
- `github.com`: actualización y revisión de código fuente.
- Cualquier otra conexión saliente se considera una violación de seguridad.

### 5.2 Procedimiento de revocación (Kill Switch)
1. Para revocar un proyecto o credencial comprometida:
   - Abrir `config/tokens.json`.
   - Modificar `"revoked": true` en el proyecto afectado.
   - Guardar el archivo. El gateway recarga la tabla en caliente y rechaza
     nuevas peticiones con `403 credential_revoked`.
2. Para parada total de emergencia:
   - Ejecutar `bash run/stop.sh`. Todos los listeners y subprocesos se detienen.
   - *Nota de implementación I2-P*: el script `run/stop.sh` actual detiene el
     puerto 8091; su ampliación para cubrir coordinadamente los listeners 8092
     y 8443 forma parte de los entregables de código de TAREA I2-P.

### 5.3 Procedimiento de Rollback
Si la Fase I2 presenta inestabilidad o problemas de seguridad:
1. Detener el terminador TLS en el puerto 8443.
2. Restablecer el gateway a modo loopback local uniusuario (Fase I1-V).
3. Confirmar que `127.0.0.1:8092` responde exclusivamente en localhost.
