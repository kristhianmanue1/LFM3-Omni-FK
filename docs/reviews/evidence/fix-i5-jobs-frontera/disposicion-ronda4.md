# Disposición de la ronda 4 — fix-i5-jobs-frontera (2026-11-08)

## Revisión

opencode GLM-5.3 hizo la revisión fresca de la ronda 4 y dio el veredicto
**proceed**. Es de la misma familia que el ejecutor.

- **Origen:** recurrí a GLM porque Codex agotó su cuota dos veces y el
  capitán de relevo dio esa instrucción. **No es una excepción
  autorizada por el Operador.** Un registro anterior de este archivo y
  de los mandatos de revisión de las rondas 2 y 4 se la atribuía al
  Operador, y eso queda corregido aquí.
- **Sustitución:** el Operador exige una revisión pre-merge de agy
  (Gemini, otra familia), en sólo lectura y con contexto fresco. **Ese
  proceed sustituye al de GLM**, y se integra sólo con él.
- **Informe GLM:** `…/scratchpad/lfm3/ola2/fix-i5-rev4-glm/informe.md`,
  fuera del repositorio.

## [MED] `202` sin despacho tras `OSError` del worker

- **Disposición:** **aceptado por escrito como residual por el
  Operador**. Ver `aceptacion-riesgo.md`.
- **Seguimiento:** tarea `fix-i5-despacho`, en la próxima ola de I5.

## [LOW] `_resolver_rival` sin `_asegurar_despacho`

Con D1 es inalcanzable: hay un solo escritor del árbol de idempotencia y
`lookup`→`commit` va bajo `self.lock`. Queda como seguimiento en
`fix-i5-despacho`, que debe alinear la rama o anotarla como defensiva
exclusiva de D1.

## Seguimientos ya declarados

- LOW-7: reloj inyectable.
- `test_r13` de `test_ciclo_arranque`: es sensible a la suspensión del
  equipo porque usa un plazo de reloj de pared. Va con `stop-pidfile`.
- Cifrado en reposo (desviación declarada D3): bloquea exponer `/jobs`.
