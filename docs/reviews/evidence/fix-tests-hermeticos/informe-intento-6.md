# Informe — fix-tests-hermeticos, intento 6 (mínimo)

Ejecutor: agente en worktree
`/Users/krisnova/www/AGTexperts/externos/LFM3-Omni-wt-fix-tests-hermeticos`,
rama `agent/fix-tests-hermeticos`, HEAD `5032fe9` (intentos 1-5 en commit;
este intento queda sin commit para el capitán). Intento MÍNIMO: sólo el
[MED] de la ronda 5 (borrado de emergencia silencioso); nada más se toca.
Prohibiciones respetadas: ningún `kill`/`pkill`/`stop.sh` propio contra
procesos o puertos reales, motor real no arrancado, alcance limitado a
`tests/` y este expediente.

## Disposición del hallazgo de la ronda 5

**[MED] El borrado de emergencia puede fallar sin dejar constancia** —
**fixed.**

- Antes (`tests/hermetic_fixture.py:365-377` viejo): el constructor
  atrapaba cualquier fallo de `_prepare`/`_write_substitutes` y llamaba
  `shutil.rmtree(self.tmp, ignore_errors=True)` antes de repropagar. Con
  `ignore_errors=True` un fallo real de filesystem era invisible (tmp
  huérfano, cero constancia); y si el borrado llegaba a elevar su error,
  corría DESPROTEGIDO dentro del `except` y SUSTITUÍA al error de
  preparación. El control de la ronda 4 sólo cubría el borrado exitoso.
- Ahora (`tests/hermetic_fixture.py:365-385`): el borrado es estricto
  (sin `ignore_errors`) y queda dentro de su propio `try/except`. Si
  falla, el error de borrado NO se pierde ni sustituye a nadie: viaja
  adjunto al error ORIGINAL con `add_note` (Python >= 3.11; el host corre
  3.15.2), con la ruta del tmp conservado y su motivo, y el `raise`
  final repropaga EL MISMO objeto de preparación — sin cambio de tipo,
  sin cambio de motivo.
- **RED antes de corregir** (`red-intento-6.txt`): el control nuevo,
  corrido contra el código viejo, falla exactamente en la identidad:
  `OSError('fallo inducido en rmtree') is not OSError('fallo inducido en
  la preparación')` — el error propagado era el de borrado (enmascaramiento
  determinista de la mitad del defecto; la otra mitad, el silencio de
  `ignore_errors`, es la que la revisión describió). El tmp que el control
  roto dejó en `${TMPDIR}` se retiró a mano antes del GREEN (un solo
  directorio `hermetic-selfclean2-*`, verificado ausente después).
- **Control determinista nuevo**
  (`tests/test_hermetic_fixture.py:231-272`,
  `SelfCleaningConstructor.test_prepare_and_rmtree_failure_keeps_both_reasons`):
  con `mock` fallan a la vez `_write_substitutes` (preparación) y
  `shutil.rmtree` (borrado de emergencia). Exige: (a) identidad — el
  error propagado ES el objeto de preparación (`assertIs`); (b) su motivo
  en el mensaje; (c) el motivo de `rmtree` presente en `__notes__`;
  (d) exactamente un tmp conservado con el prefijo del control; (e) la
  RUTA de ese tmp nombrada en la nota; y (f) al final limpia el tmp real
  que dejó el borrado fallido (`rmtree` explícito, ya sin mock, más una
  red de seguridad `addCleanup` para que ni un fallo de aserción filtré
  el directorio).

## Cambios por archivo (intento 6)

- `tests/hermetic_fixture.py` (707→715): sólo el constructor —
  `except BaseException as preparation_error`, `shutil.rmtree(self.tmp)`
  estricto en `try/except Exception`, `add_note` con ruta y motivo del
  fallo de borrado, `raise` del original. Nada más.
- `tests/test_hermetic_fixture.py` (232→276): `import shutil` y el
  control nuevo de la clase `SelfCleaningConstructor`. Nada más.
- Expediente: `capturar-intento-6.py` (envoltorio de fotos, igual que el
  del intento 5), `red-intento-6.txt`, `focal-intento-6.txt`,
  `green_suite_1/2-intento-6.txt`, `mutantes-intento-6.txt`,
  `green_checks_git-intento-6.txt`, este informe.

## Salida real de las verificaciones

- **RED**: 1 test, FAIL por `assertIs` (`red-intento-6.txt`); rc=1.
- **Focal** `tests.test_hermetic_fixture -v` (`focal-intento-6.txt`):
  **9 tests, OK** (8 previos + el control nuevo); fotos lsof/ps limpias
  antes y después.
- **Suite completa ×2** (`green_suite_1/2-intento-6.txt`):
  `Ran 322 tests, OK (skipped=2)` en 124,2 s y 124,5 s (321 del intento 5
  + el control nuevo). Fotos lsof/ps antes, entre (el «antes» de la
  segunda) y después: `(ninguno)` en las seis.
- **Mutación** (`mutantes-intento-6.txt`, `mutacion-intento-5.sh` sobre
  clon, una sola ejecución): BASELINE test_11/sonda/r17b rc=0;
  **MUTANTE 1 muere, 2 muere, 3 muere, 4 muere**.
- **Gates y git** (`green_checks_git-intento-6.txt`):
  `check_sizes`/`check_plans`/`check_reports` rc=0 (ruta de lectura
  1799/1800, preexistente), drift del kit ×2 rc=0, `git diff --check`
  rc=0, `git status --porcelain` acotado a `tests/` + expediente.
- **Sin restos**: cero `hermetic-*` y cero `mutacion-i5.*` en
  `${TMPDIR}`; cero procesos del fixture (`pgrep`).

## Propiedades P1-P3 (continuidad)

- **P1** — **pass**: fotos limpias; mutantes 1, 2 y 4 mordiendo; el
  cambio no añade ninguna ruta de señal (solo `add_note` sobre una
  excepción que ya viajaba).
- **P2 sin motor** — **pass** (`skipped=2` en ambas suites). **P2 con
  motor** — **inconclusive** (sin motor; arrancarlo está prohibido) —
  atribución heredada.
- **P3** — **pass** (322 OK ×2, resultado idéntico).

## Decisiones abiertas (recomendación primero)

1. **`add_note` como mecanismo de adjunto** (requiere Python >= 3.11).
   - *Recomendada*: `add_note` directo. Por qué: lo autoriza el mandato
     («usa add_note (Python >= 3.11) o un equivalente explícito»), el
     python3 del host es 3.15.2, y `__notes__` ya se imprime en los
     tracebacks estándar (el diagnóstico llega solo al caller). Coste de
     la alternativa (atributo propio en la excepción): reinventar un
     mecanismo estándar y perder esa impresión nativa.
2. **`except Exception` (no sólo `OSError`) alrededor del borrado de
   emergencia.**
   - *Recomendada*: `Exception`. Por qué: la propiedad exigida es que
     NINGÚN fallo del borrado sustituya al error de preparación; si rmtree
     elevase algo no-OSError, con `except OSError` volvería a enmascarar
     (el defecto exacto de este hallazgo). Coste de la alternativa:
     brecha teórica mínima, pero es la brecha que el control prohíbe.
3. **Riesgo residual heredado del PID reciclado dentro del mismo
   segundo** (ronda 5 lo deja como decisión del Operador, sin hallazgo
   nuevo).
   - *Recomendación heredada sin cambio*: aceptar la formulación acotada
     de P1 para esta entrega y decidir aparte el endurecimiento de
     `run/stop.sh` (pidfile + hora de inicio registrada al arrancar).

## Riesgos

- Heredados del intento 5, sin cambio: identidad `exec -a` dependiente
  de node; ventana mínima lectura-lstart→señal (residual nº 3 arriba);
  vigilancia atada a `BASH_ENV`; fidelidad de los sustitutos al
  mecanismo de descubrimiento actual de `run/`; dependencia de los
  textos literales de `run/serve.sh` en r17b/r17c.
- Nuevos, ninguno conocido: la nota adjunta sólo viaja con la excepción
  (no altera el control flow) y el comportamiento con borrado exitoso es
  idéntico al de antes (control de la ronda 4 sigue en verde).

No se hizo commit: el capitán lo hace tras auditar.
