# Disposición de la ronda 4 — fix-i5-jobs-frontera (2026-11-08)

Revisión fresca de la ronda 4, hecha por opencode GLM-5.3. Es de la
misma familia que el ejecutor, como excepción autorizada por el
Operador: Codex agotó su cuota dos veces. Veredicto: **proceed**.
Informe completo en
`…/scratchpad/lfm3/ola2/fix-i5-rev4-glm/informe.md`, fuera del repo.
La ronda 3 queda cerrada con tests que fallan si se revierte cada fix, y
la reorganización `50f9a5b` es pura.

## [MED] `202` sin despacho tras `OSError` del worker

- **Caso.** Cualquier `OSError` entre sacar el job de `work_queue` y
  persistir `running` deja el job `queued` en disco y fuera de la cola,
  pero dentro de `_en_cola`. Un reintento con la misma clave responde
  `202` sin avance (`src/jobs_manager.py:555`, `:593-595`, `:176-192` y
  `:612-631`). El revisor lo reprodujo con dos sondas.
- **Impacto acotado:**
  - exige un fallo de disco justo en esa ventana;
  - no hay doble ejecución ni impacto de privacidad;
  - se autocorrige cuando vence el TTL (1 h por defecto) o al reiniciar
    (`startup_recover` reencola);
  - `/jobs` no está expuesto (D3 lo bloquea).
- **Disposición propuesta:** **diferido como residual declarado**, que
  amplía el residual 3 de `informe-intento-4.md` a «cualquier `OSError`
  en esa ventana».
- **Corrección de seguimiento,** que es la recomendada por el revisor y
  es pequeña. Al abandonar un job ya retirado de la cola sin haber
  persistido `running`, releer el job bajo `self.lock`. Si sigue
  `queued`, sacarlo de `_en_cola` para que el siguiente reintento lo
  reencole. Si la relectura falla, se mantiene el comportamiento actual,
  que es fail-closed. Tarea: `fix-i5-despacho`, en la próxima ola de I5.
- **Estado:** pendiente de la aceptación del Operador.

## [LOW] `_resolver_rival` sin `_asegurar_despacho`

Con D1 es inalcanzable: un solo escritor del árbol de idempotencia, con
`lookup`→`commit` bajo `self.lock`. Queda como seguimiento en la misma
tarea `fix-i5-despacho`: alinear la rama, o anotarla como defensiva
exclusiva de D1.

## Seguimientos ya declarados

- LOW-7, reloj inyectable.
- `test_r13` de `test_ciclo_arranque`, sensible a la suspensión del
  equipo: plazo de reloj de pared. Va con `stop-pidfile`.
- Cifrado en reposo, desviación declarada D3: es bloqueante para
  exponer `/jobs`.
