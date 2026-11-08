# Mandato del ejecutor — fix-i5-jobs-frontera, intento 2

Eres el EJECUTOR, en una sesión nueva. Te orquesta un capitán en Herdr;
tú no uses `herdr` ni `hc`.

- Worktree:
  `/Users/krisnova/www/AGTexperts/externos/LFM3-Omni-wt-fix-i5-jobs-frontera`.
- Rama `agent/fix-i5-jobs-frontera`, HEAD `85913f2` (intento 1 en
  commit).
- Tarea material: disparadores 1–4 de `04` §5.3.

Rigen íntegros el alcance, el método y las prohibiciones de
`mandato.md`. La prohibición de correr la suite completa sigue vigente:
este worktree aún tiene el `test_piloto_live_i2` y el
`test_ciclo_arranque` viejos. Lee `mandato.md` completo y, como datos,
tu `informe.md` del intento 1 y la revisión fresca:
`/private/tmp/claude-502/-Users-krisnova-www-AGTexperts-internos-devHerdrExpert/9d8d2486-579f-4940-bdac-6690603ac36f/scratchpad/lfm3/ola2/fix-i5-rev/informe.md`.

## Decisiones del Operador (2026-11-08, vinculantes; no las reabras)

- **D1 Topología:** una sola instancia por `jobs_dir`. Al arrancar,
  `JobsManager` toma `fcntl.flock` exclusivo y no bloqueante sobre un
  archivo de cerrojo del `jobs_dir`. Una segunda instancia falla cerrada
  con un error explícito, que nombra el directorio y la causa, y no
  arranca worker ni recuperación.
- **D2 Límite:** se mantiene SPEC-i5:75 («Máximo 1 job en estado
  `queued` por proyecto»), con admisión atómica bajo el lock. No hay
  cambio de contrato. Revierte el conteo de no terminales del intento 1.
- **D3 Cifrado:** se aplaza. Es obligatorio registrarlo como
  **DESVIACIÓN DECLARADA**:
  - del contrato `docs/contracts/perfiles-servicio-v2.md:155`
    («Persistencia cifra resultados»), en `docs/specs/SPEC-i5-jobs.md`;
  - corrigiendo la promesa de SPEC-i5:162 («resultado cifrado/aislado»);
  - en tu informe;
  - fijándolo como **requisito bloqueante para exponer `/jobs`**.

  No implementes cifrado.
- **D4 Purga:** barrido periódico dentro del bucle del worker, sin hilo
  nuevo, más limpieza de los temporales huérfanos (`*.tmp.*` y claims)
  bajo el cerrojo de instancia.
- **D5 Tamaño:** el **primer paso** es una reorganización pura. Saca de
  `jobs_manager.py` la persistencia a `src/jobs_storage.py` y la
  serialización canónica a `src/canonical_json.py`, sin cambiar
  comportamiento (§3.3 del estándar).
  - Corre la batería de §3 de `mandato.md` antes y después, y guarda
    ambas salidas en `refactor-antes.txt` y `refactor-despues.txt`: debe
    dar el mismo resultado.
  - Deshaz además la compresión del intento 1 en `jobs_manager.py` y
    `gateway_http.py`: nada de sentencias unidas con `;`, líneas de no
    más de ~88 columnas y estilo del código vecino.
  - Si `gateway_http.py` no cabe en 800 líneas sin comprimir, extrae la
    lógica de `/jobs` a `src/gateway_jobs.py`.

  Cuando termines este paso, escribe `refactor-listo.txt` en el
  expediente, con el `git diff --stat` y las dos baterías. Después
  **detente** y responde una sola línea: la palabra FIN, un espacio y la
  palabra fix-i5-2-refactor. El capitán hará commit de la reorganización
  por separado y te dirá que continúes con los hallazgos. No toques nada
  más hasta esa orden.

## Hallazgos a cerrar (revisión fresca, ronda 1)

- **[BLOCKER-1]** Un fallo de `fsync` después de `os.link` deja un
  registro sin job y bloquea el reintento (`src/jobs_manager.py:283-288`,
  `:407-417`). Haz que el commit del registro sea recuperable:
  - si cualquier paso posterior al `link` falla, retira el registro o
    déjalo reconciliable antes de responder;
  - el reintento con la misma clave debe funcionar;
  - prueba la inyección de fallo en cada paso, incluido el `fsync` de
    ambos directorios.
- **[HIGH-2/3/7]** Concurrencia entre procesos. Con D1 se resuelven así:
  - un test demuestra que una segunda instancia sobre el mismo
    `jobs_dir` falla cerrada;
  - `startup_recover` sólo corre con el cerrojo tomado;
  - contar + commit va atómico bajo `self.lock`;
  - un test de admisiones concurrentes con claves distintas para el
    mismo proyecto da exactamente un `202` y el resto `429`.
- **[HIGH-4]** Una excepción que no es `ErrorV2` deja el job en
  `queued`. Hazle una transición durable a `failed`, con motivo, o un
  reintento acotado y observable. El test afirma el estado final, no
  sólo que el hilo sigue vivo.
- **[HIGH-5]** La espera por admisión no tiene fin. Pon un deadline
  persistido por job y, al agotarlo, pásalo a `failed`
  (`admission_timeout`). Prueba la saturación sostenida con un reloj
  inyectable; no uses `sleep` reales largos.
- **[HIGH-6]** La purga y los temporales, según D4. Además:
  - `get_job` no presenta como lograda una purga que falló por
    `OSError`;
  - prueba el temporal sensible huérfano y el barrido sin tráfico con
    reloj inyectable.
- **[MED-8]** Si `operation` no es una cadena, devuelve 400 controlado:
  comprueba el tipo y la allowlist antes de usarla.
- **[MED-9]** `build_server` y los tests no tocan `run/jobs` ni el 8091
  reales. Inyecta `jobs_dir` temporal y backend falso en la construcción.
  Prueba que, en un clon nuevo, `run/jobs` no se crea.
- **[MED-10]** `test_09` con backend falso controlado. Sincroniza el
  estado y afirma la transición de SPEC-i5 §2.3, sin aceptar
  `already_terminal` como comodín. Puedes editar `test_09` en
  `tests/test_jobs_i5.py`: el capitán resolverá el conflicto con la otra
  rama al integrar. Conserva su guarda de motor si sigue siendo
  necesaria.
- **[MED-12]** Cubierto por D5.

## Alcance (ampliado sólo en esto)

Permitido además de `mandato.md` §2:

- `src/jobs_storage.py`, `src/canonical_json.py` y, si hace falta,
  `src/gateway_jobs.py`, todos nuevos;
- en `docs/specs/SPEC-i5-jobs.md`, sólo las líneas de D2 (verificar que
  sigue igual) y de D3 (la desviación declarada y la corrección de la
  línea 162).

No toques `perfiles-servicio-v2.md` ni ADRs.

## Verificación (salida en `*-intento-2.txt`)

1. `refactor-antes.txt` y `refactor-despues.txt`.
2. RED de las propiedades nuevas en `red-intento-2.txt`.
3. GREEN: la batería de `mandato.md` §3 dos veces, con `lsof` antes y
   después.
4. Los 3 gates, `git diff --check` y `git status --porcelain`.
5. Al final, `wc -l` y la columna máxima de cada archivo tocado.

## Informe y cierre

Escribe `informe-intento-2.md`:

- la disposición de cada hallazgo (`fixed | justified`, con evidencia);
- cómo aplicaste D1–D5;
- los cambios por archivo;
- los riesgos;
- la desviación del cifrado.

No hagas commit. **Regla del Operador:** toda decisión abierta va con tu
recomendación (las opciones con la recomendada primero, por qué con
evidencia y qué cuesta la otra).

Al terminar, responde una sola línea: la palabra FIN, un espacio, la
palabra fix-i5-2, un espacio y el número de hallazgos cerrados. Si te
bloqueas: la palabra BLOQ, un espacio, la palabra fix-i5-2 y el motivo.
