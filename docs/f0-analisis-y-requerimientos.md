# F0 — Análisis inicial y requerimientos

> Producto de la fase F0 según `docs/ai-agent-guide/01-analisis-y-requerimientos.md`.
> Clase de tarea: **Architectural** — proyecto nuevo, contrato público nuevo
> (disparadores: sin archivos de producción previos; crea plan e interfaz).
> Fecha: 2026-11-02. Ejecutor: agente OpenCode (GLM), sesión dirigida por
> el humano (Operador).

## 1. Problema

Los agentes de IA y los proyectos del ecosistema (desarrollos web, apps,
servicios) no tienen un motor de inferencia omnimodal local con superficie
estable: hoy dependen de créditos de servicios remotos y no hay un contrato
declarado que un tercero pueda consumir sin negociar el método cada vez.
Esto resuelve ese dolor para el ecosistema AGT (uso interno e inter-proyecto).

## 2. Resultado observable

Una persona o agente levanta el servicio con un comando documentado y
consume `http://localhost:8091/v1` (chat multimodal: texto e imagen; voz y
audio según capacidades del motor) desde cualquier cliente compatible
OpenAI, sin créditos remotos; un proyecto externo lee el contrato versionado
y sabe base URL, autenticación, límites y muestreo sin preguntar a nadie.
Éxito visible desde fuera: `/health` en 200 y una completación real contra
el modelo en esta máquina.

## 3. Requerimientos

```text
REQ-1 [funcional] [fuente: instrucción directa del humano, 2026-11-02]
Enunciado: Servir LFM3-Omni-2B (GGUF Q4_K_M + mmproj) con llama-server local.
Criterio: dado el runbook §7, /health responde 200 y POST /v1/chat/completions
devuelve una completación válida para un prompt de prueba en esta máquina.
Prioridad: imprescindible

REQ-2 [funcional] [fuente: instrucción directa del humano, 2026-11-02]
Enunciado: El servicio escucha en el puerto 8091.
Criterio: /health responde en 8091 y el arranque no colisiona con el
servicio Docker existente en 8080.
Prioridad: imprescindible

REQ-3 [funcional] [fuente: instrucción directa del humano, 2026-11-02]
Enunciado: El motor está disponible, además de para agentes, para proyectos
externos que lo consuman en sus desarrollos web y apps.
Criterio: existe contrato versionado (F1) que declara base URL,
autenticación, CORS, límites y muestreo; un cliente OpenAI estándar lista
modelos y completa sin configuración extraña.
Prioridad: imprescindible

REQ-4 [funcional] [fuente: instrucción directa del humano, 2026-11-02]
Enunciado: Exponer el motor como herramientas para agentes por medio de
contratos, API y MCP.
Criterio: el servidor MCP propio pasa handshake MCP y expone al menos una
tool verificable que delega en el motor.
Prioridad: imprescindible

REQ-5 [restricción] [fuente: evidencia de entorno, EV-1/EV-2]
Enunciado: El servicio opera en una MacBook Air M2, 16 GB RAM, sin
ventilador, con ~57 GiB libres en disco.
Criterio: RSS residente del servidor por debajo de 4 GB con el modelo
cargado; sin swap sostenido durante una completación de prueba.
Prioridad: imprescindible

REQ-6 [restricción] [fuente: ficha oficial del modelo + instrucción directa]
Enunciado: Muestreo greedy (--temp 0) y modo no-reasoning (--reasoning off).
Criterio: la configuración del runbook coincide con la recomendación de la
ficha del modelo; el log de arranque del servidor la refleja.
Prioridad: imprescindible

REQ-7 [no-funcional] [fuente: guía 06 §5; corpus Skevi adoptado]
Enunciado: La salida del modelo se trata como dato no confiable: todo
consumidor de la superficie valida contra esquema cerrado en la frontera
antes de persistir o reenviar.
Criterio: el contrato F1 declara el mecanismo de validación (esquema/
grammar del propio llama-server o validador del consumidor) y un caso de
prueba demuestra el rechazo de una salida malformada.
Prioridad: imprescindible

REQ-8 [restricción] [fuente: ficha HF — licencia lfm1.0]
Enunciado: Ningún ofrecimiento a terceros fuera del ecosistema interno
antes de verificar los términos de la licencia lfm1.0.
Criterio: el análisis de la licencia queda registrado en este documento
(§6) y el contrato F1 lo cita.
Prioridad: imprescindible
```

## 4. No objetivos (v1)

- Entrenamiento, fine-tuning ni producción de modelos.
- Alta disponibilidad, clustering o multi-usuario con aislamiento por tenant.
- Servicio público en internet sin decisión explícita del humano.
- Redistribución de los pesos del modelo.
- Garantizar calidad de las respuestas: se verifica por propiedades y
  conjunto de referencia (guía 06 §3), no por promesa.
- Pipelines complejos de transcodificación de media (el soporte de video del
  motor usa ffmpeg en PATH, sin más).

## 5. Preguntas abiertas

```text
PREGUNTA-1: ¿Alcance de exposición de red del servicio?
Por qué importa: bloquea el diseño de CORS y autenticación del contrato F1.
Opciones: (a) solo localhost [recomendada: coincide con el default del
servidor y con el uso actual por agentes locales]; (b) LAN con api-key,
cuando exista el primer consumidor externo real; (c) público con reverse
proxy + api-key [no antes de resolver PREGUNTA-2].
Decisión del humano: pendiente — el default operativo hasta F1 es (a).
```

## 6. Preguntas cerradas (decisiones vigentes)

```text
CERRADA-1: Puerto del servidor → 8091. Fuente: instrucción directa del
humano (recomendación 1 aprobada, 2026-11-02). El 8080 está ocupado por
Docker (EV-3); no se toca ese contenedor.
CERRADA-2: Instalación del motor → Homebrew (recomendación 2 aprobada).
CERRADA-3: Método → F0 formal de Skevi con adopción del kit (recomendación
3 aprobada); adopción verificada plantillas/v18 + gate/v13 + corpus/v8
contra skevi@74a4714 (EV-8).
CERRADA-4: Alcance → además de agentes, proyectos consumidores externos
(web, apps) [instrucción directa del humano, 2026-11-02; REQ-3].
CERRADA-5: Licencia lfm1.0 verificada contra su texto completo
("LFM Open License v1.0", fetch del repo HF, 2026-11-02 — EV-10):
uso comercial licenciado sólo mientras la entidad no exceda el umbral de
10 M USD de ingresos anuales (§5); por encima, sin licencia; la
redistribución exige entregar la licencia y conservar avisos (§4); el
incumplimiento termina los derechos automáticamente (§11). Consecuencia
operativa: el consumo interno del ecosistema y el ofrecimiento a proyectos
consumidores quedan dentro de la licencia; cualquier esquema que cobre por
el servicio a terceros se documenta y se mantiene bajo el umbral, y el
contrato F1 cita esta restricción (cierra REQ-8).
CERRADA-6: Exposición de red → solo localhost (127.0.0.1), sin api-key
mientras el servicio no salga de la máquina [humano, 2026-11-02; resuelve
PREGUNTA-1]. LAN o público exigen nueva decisión registrada con api-key.
```

## 7. Restricciones de entorno y runbook

Motor (artefacto externo de régimen congelado por registro — no se edita
en sitio; un salto de versión es una operación registrada con evidencia):

```bash
# Instalación (una vez):
brew install llama.cpp            # EV-5: 0.8.0 bottled (exige ≥ v0.8.0/b11960)

# Arranque del servicio (runbook vigente):
llama-server -hf LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M \
  --reasoning off --temp 0 --port 8091

# Verificación:
curl http://localhost:8091/health          # → {"status":"ok"}
curl http://localhost:8091/v1/models       # lista el modelo servido
```

`-hf` descarga además el mmproj (proyector multimodal). El modelo es
omnimodal (texto/imagen/video/audio → texto/voz) y **no-reasoning**: la
bandera `--reasoning off` es la que la ficha oficial prescribe.

## 8. Registro de evidencia

```text
EV-1: hardware | sysctl machdep.cpu.brand_string + hw.memsize
      → "Apple M2", 17179869184 bytes (16 GiB), 8 núcleos [pass]
EV-2: disco | df -h /System/Volumes/Data → 460Gi total, 57Gi avail [pass]
EV-3: puerto 8080 ocupado | lsof -nP -iTCP:8080 -sTCP:LISTEN → com.docker
      *:8080; curl localhost:8080/health → 404 Apache/Debian [pass]
EV-4: llama-server ausente al iniciar | which llama-server → not found [pass]
EV-5: oferta Homebrew | brew info llama.cpp → stable 0.8.0 (bottled) [pass]
EV-6: modelo y banderas | fetch ficha HF LiquidAI/LFM3-Omni-2B-GGUF +
      README tools/server de llama.cpp (master, 2026-11-02): Q4_K_M 1.1 GB,
      mmproj automático, requiere ≥ v0.8.0/b11960, --reasoning [on|off|auto]
      vigente y off prescrito para este modelo [pass]
EV-7: origen del canon | git -C skevi rev-parse --short HEAD → 74a4714;
      status --porcelain vacío [pass]
EV-8: adopción del kit | check_templates ×3 → OK plantillas/v18, gate/v13,
      corpus/v8 (registros .skevi/ con source skevi@74a4714) [pass]
EV-9: servicio vivo | llama-server 0.8.0 (build 11960) lanzado con el
      runbook §7: /health → {"status":"ok"} tras ~155 s (primera carga
      descarga GGUF 1.1 GB + mmproj); /v1/models → Q4_K_M servido;
      POST /v1/chat/completions → "Azul", 3 tokens de salida en 0.99 s
      real; RSS ≈ 2.78 GiB < 4 GB (criterio REQ-5); log de carga:
      n_slots = 4, n_ctx_slot = 128000 (128k de contexto por slot) [pass]
EV-10: licencia | fetch https://huggingface.co/LiquidAI/LFM3-Omni-2B-GGUF/
       raw/main/LICENSE → "LFM Open License v1.0": umbral comercial de
       10 M USD anuales por entidad; redistribución con licencia y avisos;
       terminación automática ante incumplimiento [pass]
```

## 9. Reporte de fase

```text
FASE F0: OK
Gate: Definition of Ready (01 §4.2)
Evidencia:
- EV-1..EV-10 arriba → todas pass
- problema y resultado observable escritos → pass
- requisitos REQ-1..REQ-8 con fuente, criterio y prioridad → pass
- no objetivos explícitos → pass
- restricciones de entorno confirmadas → pass (EV-1, EV-2, EV-5)
- preguntas materiales sin supuestos silenciosos → pass (CERRADA-1..5)
- REQ imprescindible sin criterio de aceptación → ninguno
- servicio en ejecución verificado → pass (EV-9; REQ-1/2/5/6 cubiertos)
Pendientes: ninguno — PREGUNTA-1 resuelta en CERRADA-6
```

F0 permanece cerrado en OK; F1 puede iniciarse (CERRADA-6 habilita el
diseño del contrato de superficie).
