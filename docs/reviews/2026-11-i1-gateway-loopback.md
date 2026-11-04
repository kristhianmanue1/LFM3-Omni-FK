# Ronda I1 — Gateway común en loopback (PLAN LFM3-2)

Cierre de I1-D/I1-A/I1-U: gateway modular sobre el núcleo de políticas
de I0 (`gateway_core` sin transporte + `gateway_http` de transporte,
ADR-005), capabilities que jamás anuncian lo no activo, límites de
transporte antes de costo (compresión y chunked rechazados sin leer),
allowlist único de enrutado derivado de `RUTAS_PERMITIDAS`, colisión
de puerto con fallo cerrado, y cliente de referencia
(`examples/cliente_i1.py`). SPEC: `docs/specs/SPEC-i1-gateway-loopback.md`.

Ronda adversarial doble con contexto fresco real:
- **Ronda 1** (implementación completa): veredicto fix-and-retry —
  0 BLOCKER/HIGH, 2 MED (puerto sin parse fail-closed; allowlist
  decorativo no consumido por el enrutado) y 7 LOW. Ambos MED
  corregidos; LOWs corregidos o declarados (alias `//` de la stdlib,
  HEAD por stdlib, dims declaradas, higiene de sockets).
- **Ronda 2** (verificación de fixes, con mutation testing): veredicto
  **proceed** — 33 tests OK, 12 probes propios OK, 3 mutaciones todas
  cazadas por los tests, checksums del árbol intactos. Quedan 4 LOW de
  seguimiento no bloqueantes (orden TE-antes-de-CL sin test dedicado,
  rama else muerta defensiva, banner con puerto 0, camino feliz POST→200
  acreditado por la demo G8 en lugar de la suite).

```text
id = i1-gateway-loopback-2026-11-04
date = 2026-11-04
time_utc = 20:30:00Z
head_sha = e0e7d8fe935e204f116ea5dcbf4b31a51281a23c
model = zai-coding-plan/glm-5.3-flash
STATE = OK
GATE = 5/5 gates OK; suites I1+I0+B-T10 40 tests OK (7 skips de ciclo por motor vivo, motivo verificado); golden --rapido 11 pass 0 fail; suite v1 MCP OK; demo cliente 7/7 con motor real
PENDING = D-02..D-07 antes de sus gates; I2 requiere dossier y decisiones; 4 LOW de ronda 2 como seguimiento no bloqueante (SPEC/registro)
DECISION = proceed
OPERATIONS = commit de TAREA en rama y merge ff a main + push a origin/main (autorizado por el Operador para esta sesion)
AUTHORITY = encargo del Operador 2026-11-04 «adelante con pendientes» (I1 local); ADR-005; SPEC-i1
RISK = bajo: loopback 8092; motor v1 en 8091 intacto; rollback por revert del commit
EVIDENCE
- RED de I1 antes de codigo (i1-red.txt: modulo inexistente) -> pass
- suites gateway+fachada+B-T10+ciclo 40 tests OK (i1-green-final.txt) -> pass
- ronda adversarial 1 fix-and-retry con 2 MED corregidos y 7 LOW dispuestos -> pass
- ronda adversarial 2 proceed con mutation testing y probes propios -> pass
- cliente de referencia 7/7 texto/JSON/imagen/capabilities/rechazo con motor real (i1-cliente.txt) -> pass
- golden del motor 11 pass 0 fail y suite v1 MCP OK (i1-golden.txt, i1-suite-v1.txt) -> pass
- cinco gates AGENTS en verde al estado final (i1-gates.txt) -> pass
- regresion propia de la sesion (syntax en cliente) detectada por la re-corrida y corregida -> pass
report_sha256 = 9e69fd82b0f2fa49709890011f98aabb429ef50f93922b233ac64619bae9fa13
```

## Disposición de hallazgos (ronda 1 → ronda 2)

| ID | Severidad | Hallazgo | Disposición |
|---|---|---|---|
| M-1 | MED | puerto de env inválido → traceback crudo | parse dentro del try; `(OSError, ValueError, OverflowError)` → BLOQ + exit 1; G5 ampliado con `abc`/`99999` |
| M-2 | MED | allowlist decorativo (no consumido por el enrutado) | enrutado derivado de `RUTAS_PERMITIDAS` vía `_enrutar`; G4 verifica equivalencia bidireccional |
| L-1 | LOW | alias `//healthz` por normalización stdlib | documentado en SPEC §2 (cae en ruta permitida; sin bypass) |
| L-2 | LOW | métodos no implementados → 501 HTML | PUT/DELETE/PATCH/OPTIONS → 404 JSON; HEAD documentado |
| L-3 | LOW | G3 no probaba el orden «antes de leer» | G3 reescrito sólo-cabeceras (con cuerpo colgaría) |
| L-4 | LOW | TE+CL simultáneos: TE ignorado | TE presente → 400 aunque haya CL |
| L-5 | LOW | fachada perdía nombres de módulo + import muerto | fachada completa con aliases históricos; `os` eliminado |
| L-6 | LOW | `LFM3_ADAPTER_PORT` ignorado en silencio | main acepta GATEWAY→ADAPTER→default |
| L-7 | LOW | higiene: sockets sin cerrar; URLError crudo en cliente | server_close en tearDown; cliente con fallo elegante |
| R2-L1..L4 | LOW | seguimiento ronda 2 (ver arriba) | anotados como pendiente no bloqueante |
