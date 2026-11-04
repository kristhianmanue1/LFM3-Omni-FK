# ADR-005: Stack HTTP del gateway loopback y política de puerto

```text
ADR-005: Gateway I1 sobre http.server stdlib (ThreadingHTTPServer),
puerto default 8092 configurable con fallo cerrado por colisión
Estado: aceptado (I1-D; encargo del Operador, 2026-11-04, «adelante
con pendientes»)
Contexto: I1 exige un gateway HTTP modular en loopback con las mismas
políticas que regirán MCP v2 (S-05), sin exposiciones remotas (D-03
sigue pendiente y no bloquea I1). La elección de stack compara al
menos dos alternativas con licencia y superficie (objetivo-y-alcance,
§Decisiones pendientes). El puerto 8080 de esta máquina está ocupado
por Docker del Operador (decisión registrada en F0) y no se toca.
Decisión: transporte HTTP con http.server.ThreadingHTTPServer de la
stdlib 3.12+, reutilizando el núcleo de políticas validado en I0
(ADR-004) y separándolo en dos módulos: gateway_core (políticas puras,
compartibles con un futuro adaptador MCP v2) y gateway_http
(transporte). Puerto default 8092, overridable con LFM3_GATEWAY_PORT
para tests; una colisión de puerto al arrancar falla cerrado (mensaje
BLOQ y exit 1), jamás asumir puerto libre ni tomar el 8080.
Alternativas descartadas:
  - FastAPI + uvicorn + pydantic (MIT/BSD): validación declarativa
    cómoda, pero tres dependencias externas sin autoridad de
    instalación, lockfile nuevo y reversión del registro de cascarón;
    la potencia sobra para loopback y el dialecto ya está cerrado por
    ADR-004.
  - aiohttp (Apache-2.0): modelo async que no resuelve ningún
    requisito de I1 (no hay streaming en I0/I1), misma carga de
    dependencias.
  - http.client puro sin servidor propio: I1 ES un servidor; no aplica.
Consecuencias:
  - Gana: cero dependencias; dos módulos auditables; el núcleo de
    políticas queda listo para ser consumido por MCP v2 (S-05); fallo
    cerrado ante colisión de puerto.
  - Pierde: rendimiento concurrente modesto (hilos stdlib) — explícito
    y aceptado para loopback; el benchmark de carga es I2 con D-04.
  - Queda obligado: ningún endpoint fuera del allowlist; capabilities
    jamás anuncia voz/video/streaming; el núcleo (gateway_core) no
    importa nada de transporte (test de frontera interno); cambios de
    puerto default o de dialecto exigen SPEC nuevo.
```
