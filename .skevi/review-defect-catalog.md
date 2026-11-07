# Catálogo de clases de defecto para la ronda adversarial

> Plantilla opcional — experimental (ADR-035). La aplica el ejecutor
> durante la ronda de `04` §5: da **forma comprobable** —clase, pregunta
> de ataque, evidencia esperada—, no certeza. La salida de una revisión
> asistida sigue siendo salida no determinista (ADR-024, guía `06`): este
> catálogo no la convierte en verificación por estructurarla.
>
> **Procedencia:** destilado agnóstico, redactado desde cero, derivado de
> las skills `code-review` y `debug` de Engineering 1.2.0
> (`anthropics/knowledge-work-plugins@58da91d`, Apache-2.0, verificado el
> 2026-09-18 — registro `docs/reviews/2026-09-18-prop010-procedencia.md`).
> Sin expresión literal del original. **Experimental:** se retira si su
> piloto falla o si a los doce meses de su aceptación no ha salido de
> experimental, con su línea de `ofrece` (PROP-010 §3.5).

## Cómo se usa

En la ronda adversarial, recorre las clases contra el diff real. Cada
clase es una pregunta de ataque y la evidencia que la respuesta debe
mostrar; un hallazgo sin evidencia esperada no es hallazgo, es sospecha.
Las clases son agnósticas de lenguaje y plataforma: sin términos de
framework ni de motor.

## Clases de defecto

### 1. Entrada no confiable e inyección

- **Pregunta de ataque:** ¿qué camino toma un dato que yo no controlo
  hasta llegar a algo que se ejecuta, se consulta o se renderiza — y qué
  lo valida en cada frontera?
- **Evidencia esperada:** la frontera que valida, el tipo exacto de
  validación y el rechazo del caso malicioso. Incluye salida de modelos
  o herramientas externas consumida sin revisión (LLM01/LLM05 del
  cotejo OWASP): un dato no confiable que pasa a comando, consulta o
  plantilla ejecutable sin tratar.

### 2. Autorización

- **Pregunta de ataque:** ¿qué operación puede disparar un actor que no
  debería, siguiendo el camino más corto — incluido el propio ejecutor
  automatizado?
- **Evidencia esperada:** la regla que niega el camino, dónde vive y qué
  la hace cumplir (polaridad cerrada: lo no enumerado, rechazado). La
  capacidad técnica nunca es la autorización.

### 3. Secretos

- **Pregunta de ataque:** ¿dónde puede quedar un secreto —código,
  historial, log, reporte, ventana de contexto— y qué lo saca de ahí?
- **Evidencia esperada:** la ubicación declarada de los secretos, la
  prueba de que el camino revisado no los toca, y el tratamiento como
  comprometido si alguno entró al contexto (revocación antes que
  limpieza).

### 4. Concurrencia

- **Pregunta de ataque:** ¿qué se rompe si dos ejecuciones del mismo
  camino corren a la vez, o si una se pausa justo en el peor punto?
- **Evidencia esperada:** el recurso compartido, la condición de carrera
  o interbloqueo concreta, y el mecanismo que serializa o aísla.

### 5. Recursos no liberados

- **Pregunta de ataque:** ¿qué queda abierto —archivo, conexión,
  proceso, lock, sesión— si el camino falla en cada punto donde puede
  fallar?
- **Evidencia esperada:** la adquisición emparejada con su liberación en
  el camino de error, no sólo en el de éxito.

### 6. Trabajo no acotado

- **Pregunta de ataque:** ¿qué entrada o condición hace que este trabajo
  crezca sin límite —en tiempo, memoria, costo o llamadas— y quién pone
  el tope?
- **Evidencia esperada:** el límite explícito, dónde se aplica y el
  comportamiento al alcanzarlo (fallar controlado, no colgar).

### 7. Errores silenciados

- **Pregunta de ataque:** ¿qué fallo puede ocurrir sin que nadie lo vea
  —código de salida tragado, excepción capturada y omitida, salida
  vacía tratada como éxito?
- **Evidencia esperada:** el punto donde el fallo se ignora y la vía por
  la que debió propagarse o registrarse. Un gate o check que no puede
  fallar no está verificando nada.

### 8. Contrato roto

- **Pregunta de ataque:** ¿qué promesa —nombre, firma, formato, campo,
  unidad, orden— cambió de un lado sin cambiar del otro?
- **Evidencia esperada:** el contrato escrito en ambos lados y la
  comparación byte a byte, no por resumen ni por intención.

### 9. Test que no prueba el requisito

- **Pregunta de ataque:** si invierto o rompo exactamente lo que el
  requisito pide, ¿este test se pone en rojo? ¿Qué control positivo lo
  demuestra?
- **Evidencia esperada:** la prueba de que el test detecta el defecto
  que dice detectar (control positivo), no sólo que pasa en verde.

## Diagnóstico escrito (forma del tercero tras dos fallos)

Cuando `04` §8 exige diagnóstico escrito antes del tercer intento, esta
sección le da forma — cuatro requisitos:

1. **Reproducción:** el comando o paso exacto que falla, con su salida,
   repetible por otra sesión.
2. **Aislamiento:** el caso mínimo que aún falla y lo que se descartó
   cambiando una variable a la vez.
3. **Hipótesis con su prueba:** cada explicación candidata, en una
   frase, con el experimento que la confirma o la descarta — y su
   resultado real, no esperado.
4. **Causa raíz separada del síntoma:** qué está roto y por qué se rompió
   son preguntas distintas; el diagnóstico responde ambas, y la
   corrección ataca la causa, no el síntoma.
