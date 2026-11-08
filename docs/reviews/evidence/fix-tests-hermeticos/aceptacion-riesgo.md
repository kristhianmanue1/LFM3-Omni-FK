# Aceptación de riesgo residual — fix-tests-hermeticos (2026-11-08)

## El caso

El fixture hermético (`tests/hermetic_fixture.py:81-109`) define `kill`
como función Bash mediante `BASH_ENV`. Sólo entrega una señal real si se
cumplen las dos condiciones:

- el PID está inscrito en `owned_pids`;
- la hora de inicio actual de ese PID (`/bin/ps -p PID -o lstart=`)
  coincide con la inscrita.

En cualquier otro caso la niega y la registra en `kill_denied.log`.

`lstart` tiene precisión de segundos, y la señal se entrega por número
de PID con `builtin kill`. Si un proceso propio del fixture muere y el
sistema reasigna su PID a otro proceso, el control falla en dos ventanas:

- dentro del mismo segundo de inicio;
- entre la lectura de `ps` y el `kill`.

En ambas, la comparación pasaría y la señal podría llegar al nuevo
dueño del PID.

## Por qué es residual

- Es una carrera inferida del código. No se ha observado en ninguna
  corrida.
- Para que ocurra deben coincidir tres cosas: la muerte de un proceso
  del fixture, la reutilización de su PID en la misma ventana de un
  segundo y que el nuevo dueño sea un proceso del host.
- Todas las demás vías están cerradas y probadas:
  - el entorno explícito mínimo, con `bash --noprofile --norc`;
  - los sustitutos `lsof`/`curl`, sin puertos reales;
  - la negativa del `kill` a PIDs no inscritos o con hora falsa (control
    positivo y mutante 2);
  - ninguna señal desde Python a PIDs leídos de archivo.
- Las revisiones frescas de las rondas 4, 5 y 6 lo clasifican como MED
  heredado, no como hallazgo nuevo. Las tres recomiendan aceptar la
  garantía acotada de P1 y tratar el endurecimiento aparte.
- La garantía absoluta exigiría aislar procesos o señalizar por handle
  estable, es decir, infraestructura nueva fuera del alcance de
  `tests/`.

**Garantía aceptada para esta entrega (P1 acotada):** ningún test
ejecuta scripts de `run/` del checkout, enlaza 8091/8092/8443 reales ni
señala a un PID no inscrito o con hora de inicio distinta. La salvedad
es la ventana de reutilización de PID descrita arriba.

## Decisión del Operador

Cita literal, transmitida por devherdr-expert el 2026-11-08:
«adelante». Era la respuesta a esta recomendación: aceptar como riesgo
declarado el PID reutilizado dentro del mismo segundo y encargar aparte
`run/stop.sh` por pidfile.

## Seguimiento: tarea `stop-pidfile`

`run/stop.sh` debe parar los procesos que arrancó el propio servicio
por pidfile ligado a su identidad de arranque (PID, hora de inicio
registrada y comando), no por descubrimiento global de puerto y patrón
de texto.

La ronda 6 advierte que un pidfile con `lstart` de precisión de segundos
reduce el riesgo de descubrimiento, pero no elimina por sí solo la
carrera. La tarea debe valorar una identidad más fuerte, como el grupo
de procesos o el handle del proceso padre. Queda planificada en una ola
posterior.
