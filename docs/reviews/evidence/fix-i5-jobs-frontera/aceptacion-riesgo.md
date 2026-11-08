# Aceptación de riesgo residual — fix-i5-jobs-frontera (2026-11-08)

## El caso

Si se produce cualquier `OSError` en el worker después de retirar un job
de `work_queue` y antes de persistir `running`, el job queda en este
estado:

- `queued` en disco;
- fuera de `work_queue`;
- todavía dentro del conjunto en memoria `_en_cola`.

Un reintento con la misma clave de idempotencia consulta esa memoria y
responde `202`, pero no hay ningún avance: el job no se ejecuta. Las
rutas implicadas son:

- `src/jobs_manager.py:555`, `save_job` dentro de `_marcar_running`;
- `src/jobs_manager.py:593-595`, el `except OSError` del worker;
- `src/jobs_manager.py:176-192`, `_asegurar_despacho`;
- `src/jobs_manager.py:612-631`, `_deadline_admision_vencido`.

La revisión fresca de la ronda 4 (GLM) lo reprodujo con dos sondas en su
clon.

## Por qué es residual

- Sólo ocurre si el disco falla justo en esa ventana.
- No hay doble ejecución ni impacto de privacidad.
- Se corrige solo: cuando vence el TTL (1 h por defecto) la purga cierra
  el job, y al reiniciar `startup_recover` lo reencola.
- `/jobs` no está expuesto. La desviación declarada D3, sobre el cifrado
  en reposo, lo bloquea.
- Amplía el residual 3 de `informe-intento-4.md`, que se limitaba al
  fallo transitorio del claim, a «cualquier `OSError` en esa ventana».

## Decisión del Operador

Cita literal, transmitida por devherdr-expert el 2026-11-08:

> «B: el Operador acepta el residual MED de I5 por escrito, pero ANTES
> del merge haz que agy (Gemini) revise I5 en sólo lectura, contexto
> fresco; integra sólo con su proceed.»

## Seguimiento: tarea `fix-i5-despacho`, próxima ola de I5

1. Si se abandona un job retirado de la cola sin haber persistido
   `running` (`_reclamar` devuelve `None` por `OSError`, o salta el
   `except OSError` del worker), releer el job bajo `self.lock`.
2. Si sigue `queued`, sacarlo de `_en_cola` para que el siguiente
   reintento lo reencole.
3. Si la relectura también falla, conservar el comportamiento actual,
   que es fail-closed.
4. Alinear `_resolver_rival` con `_asegurar_despacho`, que es el LOW de
   la ronda 4.
