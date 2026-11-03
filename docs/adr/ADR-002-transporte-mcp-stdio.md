# ADR-002: El servidor MCP propio usa transporte stdio

```text
ADR-002: Transporte del servidor MCP propio: stdio
Estado: aceptado — diseño vigente; implementación en F3-1 (PLAN LFM3-1)
Contexto: REQ-4 exige exponer el motor como herramientas para agentes por
medio de contratos, API y MCP. Consumidores primarios: agentes CLI
(OpenCode y equivalentes) que lanzan procesos hijos y hablan JSON-RPC por
stdin/stdout. Restricción vigente: CERRADA-6 (solo localhost; LAN o
público exigen nueva decisión con api-key).
Decisión: el servidor MCP es un proceso hijo de transporte stdio conforme
al esquema de servidores MCP estándar; habla JSON-RPC por stdin/stdout,
no abre sockets, y delega en el motor por http://127.0.0.1:8091/v1.
Alternativas descartadas:
  - HTTP+SSE (MCP remoto): habilitaría consumidores web y paneles, pero
    exige api-key, CORS explícito y una decisión de red nueva que
    CERRADA-6 no cubre; sin consumidor remoto real hoy, es generalidad
    especulativa (regla 4 de 00-INDICE). Queda como camino natural de
    una v2 con su propia decisión registrada.
  - --mcp-servers-config de llama-server: no resuelve REQ-4: ese
    mecanismo expone MCPs HACIA el modelo (el motor consume tools de
    terceros), dirección inversa a la requerida (exponer el motor como
    tool para agentes).
Consecuencias:
  - Gana: cero superficie de red nueva; instalación en cualquier agente
    CLI por registro declarativo; reutiliza el CONTRATO v1 tal cual.
  - Pierde: los paneles web futuros necesitarán un adaptador propio o la
    v2 HTTP+SSE con su decisión.
  - Queda obligado: las tools del MCP validan en frontera la salida del
    motor contra esquema cerrado (REQ-7) y no persisten conversaciones
    en v1 (stateless).
```
