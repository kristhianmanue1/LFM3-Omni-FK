# Instalación WSL: registro histórico del primer intento

Registro histórico: los bloqueos descritos abajo se resolvieron después.
El cierre posterior está en `2026-11-dell-g7-7700.md`; la capa técnica
original se conserva sin reescribir su resultado.

Se recuperó la fuente exacta y se preparó el instalador local del motor
previsto en el plan hardware. La instalación real queda pendiente: esta
sesión bloquea red, sockets y GPU. No hay inferencia verificada en esta PC.
Guía: `../instalacion-wsl.md`; contrato: `../specs/SPEC-wsl-install.md`.
Evidencia: `evidence/instalacion-wsl-2026-11-04/`.

El HEAD de abajo identifica la fuente remota, no un HEAD local: `.git`
es una reserva de solo lectura. Se verificaron los 154 archivos al
recuperarlos; 151 siguen iguales y los tres cambios posteriores son
`.gitignore`, `README.md` y `scripts/MANIFEST.json`. El resto de la
entrega son archivos nuevos de instalación, pruebas y documentación.

```text
id = wsl-install-2026-11-04
date = 2026-11-05
time_utc = 00:35:27Z
head_sha = 9c0035bbd831822f9dcc4894d3619e2ac3546cc0
model = GPT-6 (self-declared)
STATE = PARTIAL
GATE = Source restored and installer prepared; real installation and inference are not verified
PENDING = Network/DNS access; GPU device access; sockets; real downloads, CUDA compatibility, health, inference, golden and transport tests; working Git metadata; AN-KLA unavailable
DECISION = escalate
AUTHORITY = User requested repository analysis and installation in this workspace; no publication authorized
RISK = Installer synthetic tests do not establish real CUDA or model execution; audio/video gateway remains inactive
EVIDENCE
- GitHub connector at exact source commit; all 154 original blob hashes checked at recovery -> pass
- source-verification.txt: 151 original blobs unchanged, 3 intentional changes; 10 ASR fixture SHA-256 verified -> pass
- installer-red.txt: installer absent before implementation -> pass
- installer-green.txt: 6 installer integrity tests pass -> pass
- offline-tests.txt: 48 tests pass without network or sockets -> pass
- unit-final.txt: 83 tests attempted; 48 pass, 31 socket permission errors, 4 live engine failures; environment prevents integration verification -> inconclusive
- environment-check.txt: DNS unavailable, socket EPERM, GPU inaccessible -> inconclusive
- install-attempt.txt: first download fails DNS; no runtime published -> inconclusive
- golden-attempt.txt: engine request fails socket EPERM -> inconclusive
- Fresh reviewer: synthetic install/reinstall/verify/serve passes; manifest HIGH fixed; source accounting MED fixed -> pass
- Gates: see gates-final.txt for final structural verification -> pass
- Git status/diff unavailable because reserved .git is read-only and has no repository metadata; compared original source blobs instead -> inconclusive
- AN-KLA module and local store absent; no memory verification or initialization claimed -> inconclusive
report_sha256 = 3e8890a87516061f71a60695ad935ad07511f1bc54d2db241d20fa15115013ba
```

## Ronda adversarial con contexto fresco

Revisor independiente: agente `review_wsl_install`. Ejecutó los tests
focales y un ciclo install/reinstall/verify/serve con tarballs sintéticos,
red y procesos simulados. Las cuatro descargas ocurrieron una sola vez;
la reinstalación reutilizó caché; el inventario y rutas de librerías
correspondieron al destino publicado; los argumentos de arranque fijaron
alias, loopback, greedy, reasoning off y GPU. Esto prueba orquestación,
no los binarios ni pesos reales.

| ID | Severidad | Problema e impacto | Corrección | Estado |
|---|---|---|---|---|
| W-1 | HIGH | instalador ausente del manifiesto; gate de tamaños bloqueado | añadir SHA-256 local a scripts/MANIFEST.json; repetir gate | cerrado |
| W-2 | MED | guía contaba 153 originales intactos tras modificar tres archivos; procedencia incorrecta | declarar recuperación inicial y 151 originales intactos; enumerar tres cambios | cerrado |

La decisión operativa es `escalate`: los bloqueos externos impiden
completar el DoD. El código preparado puede revisarse; no se promueve
instalación ni capacidades. Siguiente acción: ejecutar los tres comandos
de la guía desde WSL con red, sockets y GPU accesibles; comprobar salud,
modelo efectivo y baterías reales antes de declarar servicio disponible.

TAREA WSL-INSTALL: PARCIAL
DoD: fuente y preparación comprobadas; ejecución real pendiente.
RED: módulo instalador ausente, registrado antes de implementación.
Rama de este cierre: no disponible; snapshot sin Git local operativo.
Hallazgos fuera de alcance: B-T8 conserva la errata documentada; I1-V,
D-08/D-09 y servicio remoto permanecen pendientes. AN-KLA no disponible.
