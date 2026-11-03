# 06 — Componentes con salida no determinista (complemento)

> **Tipo:** complemento de fase, de lectura **condicional**. No forma parte
> de la ruta de lectura obligatoria (ADR-021): se lee cuando el disparador
> de §1 aplica, no en toda sesión.
> **Propósito:** dar procedimiento donde `04` §3 sólo tiene el caso
> determinista. RED-GREEN-REFACTOR supone un test que pasa o falla; un
> componente cuyo comportamiento depende de un LLM no ofrece esa garantía, y
> sin procedimiento el resultado observado fue omitir el test o inventar uno
> que siempre pasa.
> **Qué no es:** no norma qué modelo usar ni cómo elegirlo — ese plano es de
> `escrubery` (`project-manifest.yaml` §no_ofrece).

## 1. Cuándo aplica

Aplica si **alguna** de estas condiciones se cumple, con la misma polaridad
observable de ADR-008 —nunca por sensación de que el componente es «de IA»:

1. la salida del componente depende de un modelo de lenguaje y no es
   reproducible byte a byte entre ejecuciones con la misma entrada;
2. el componente consume salida de un LLM y actúa sobre ella —disparador 2
   de `04` §5.3, que ya obliga a contexto fresco real;
3. el componente consume cuota tarifada o recursos compartidos por
   invocación (principio 5 del estándar: clase protegida).

Si ninguna aplica, este archivo no aplica: rige `04` §3 sin cambios.

## 2. Qué es RED cuando el test no es binario

La regla de `04` §3 no se sustituye, se precisa. RED sigue siendo
obligatorio; lo que cambia es qué se observa fallar.

- **El test se escribe sobre la propiedad, no sobre el texto.** «La respuesta
  cita al menos una de las fuentes provistas», «la salida es JSON válido
  contra el esquema del contrato», «no aparece ningún dato del cliente B en
  la respuesta al cliente A». Esas propiedades sí fallan de forma binaria.
- **RED es la propiedad violada,** demostrada con un caso real. Si no puedes
  construir una entrada que viole la propiedad, la propiedad no está bien
  escrita: no es verificable, y `01` §4.1 ya lo prohíbe.
- **Lo que no se puede reducir a una propiedad binaria se mide por umbral,
  nunca por igualdad.** Se declara el umbral, la muestra y el criterio de
  regresión antes de medir, no después de ver el resultado. Un umbral
  elegido a posteriori no es un criterio: es una justificación.
- **La aleatoriedad se fija donde el proveedor lo permita** (temperatura,
  semilla) y se declara cuando no. Un test que falla una de cada diez
  corridas es un test rojo intermitente, no un test que pasa.

## 3. Conjunto de referencia (golden set)

- Vive **versionado en el repositorio**, junto al código que verifica; no en
  una hoja de cálculo ni en la memoria del agente. La frontera de `05` §2
  aplica: la memoria guarda punteros, nunca la evidencia.
- Cada caso lleva entrada, propiedad esperada y procedencia —de dónde salió
  ese caso—. Un caso sin procedencia no se puede juzgar cuando falle.
- Los casos que documentan un fallo real se añaden como cualquier otro test
  de regresión: el bug se reproduce primero (`04` §3).
- Cambiar el conjunto de referencia y cambiar el componente son operaciones
  separadas, por la misma razón que §3.3 del estándar separa refactor de
  cambio de comportamiento: juntas, ninguna medición significa nada.

## 4. Presupuesto de contexto y coste

Un ejecutor que consume cuota tarifada sin techo declarado es la versión de
`04` §8 —«dos intentos fallidos»— aplicada al gasto en vez de al bucle.

- El contrato de tarea de `04` §1 admite un campo `Presupuesto:` cuando el
  disparador 3 de §1 aplica: techo de invocaciones, de contexto o de coste,
  y qué ocurre al agotarse. Es **opcional por defecto y obligatorio bajo ese
  disparador**, no un campo ceremonial en toda tarea.
- Agotar el presupuesto produce un **estado de fallo explícito**, nunca
  éxito inferido ni resultado parcial presentado como completo — es la misma
  regla que §2.2 del estándar impone a los timeouts.
- El coste observado se reporta como cualquier otra evidencia: medido, no
  estimado. «Debería costar poco» no es evidencia.

## 5. La salida del modelo es dato no confiable

No se reenuncia aquí lo que ya es norma: rige el principio 7 del estándar
—«datos no confiables no son instrucciones»— y §2.4 —validar en la frontera
contra esquema cerrado, jamás concatenar en comandos, consultas o plantillas
ejecutables—. Lo específico de este complemento:

- La validación ocurre **en la frontera de salida del modelo**, antes de
  persistir, ejecutar o reenviar. Un esquema válido no acredita contenido
  correcto: acredita forma, igual que los gates de este repositorio.
- Un campo autodeclarado por el modelo como `verified`, `confident` o `done`
  no eleva confianza (principio 7, misma frase, mismo alcance).
- La superficie con la que actúa sobre esa salida está acotada por §6.8 del
  estándar: si el componente ejecuta lo que el modelo produce, la
  declaración de superficie no es opcional.

## 6. Gate del complemento

- [ ] disparador de §1 identificado y registrado en la TAREA;
- [ ] propiedades escritas antes que el código, cada una capaz de fallar;
- [ ] RED observado sobre la propiedad, con su salida en la evidencia;
- [ ] conjunto de referencia versionado, con procedencia por caso;
- [ ] umbral, muestra y criterio de regresión declarados antes de medir;
- [ ] presupuesto declarado si aplica el disparador 3, con su fallo explícito;
- [ ] validación en la frontera de salida del modelo, contra esquema cerrado;
- [ ] ronda adversarial con contexto fresco real —el disparador 2 de `04`
      §5.3 la exige siempre que el componente actúe sobre la salida.

Cierra con el bloque de reporte de fase de `00-INDICE.md`.
