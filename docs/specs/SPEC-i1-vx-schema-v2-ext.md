# SPEC-i1-vx — Dialecto Schema v2-ext y Percepción Multimodal Estructurada

Estado: borrador técnico para implementación TDD (F1 §2).  
Fecha: 2026-11-06.  
Procedencia: ADR-004 (enmendado por ADR-008 §1); PLAN LFM3-2 TAREA I1-VX.  
Autonomía: stdlib de Python 3.12 exclusivamente (sin jsonschema ni PyPI).

---

## 1. Contexto y Objetivos

ADR-004 estableció el dialecto cerrado `v2` en `gateway_core` para validar
tanto esquemas de entrada como salidas de inferencia (`validar_salida`) con
fail-closed estricto. ADR-008 §1 autoriza una enmienda acotada y verificable
(`v2-ext`) para dar soporte a agentes autónomos, pipelines de percepción y
adaptadores locales de dispositivos (perfil D) sin relajar la seguridad:

1. **`enum`** en propiedades escalares (`string`, `integer`, `number`,
   `boolean`): lista de 1..32 valores únicos del tipo correspondiente.
   `bool` no satisface `integer` ni `number`.
2. **`minimum` y `maximum`** en propiedades numéricas (`integer`, `number`):
   números finitos (no booleanos) con `minimum <= maximum`.
3. **`array` de profundidad 1**: `type: "array"`, con cotas `minItems` y
   `maxItems` (enteros 0..64, `minItems <= maxItems`). Los elementos (`items`)
   pueden ser escalares (con enum/cotas opcionales) u objetos planos de 1..16
   propiedades escalares.
4. **`object` anidado a nivel 1**: propiedad de tipo `object` dentro del objeto
   raíz, con `properties` (1..16 escalares) y `required` explícito. Se
   rechazan recursiones de profundidad > 1 y referencias `$ref`.
5. **Percepción estructurada multimodal**: capacidad de enviar
   `response_format` json_schema junto con `image_url` o `input_audio` en un
   solo turno, obteniendo JSON validado en frontera contra el esquema.

---

## 2. Reglas Normativas del Dialecto v2-ext

### 2.1 Validación del Esquema (`validar_schema`)

El esquema raíz debe ser un objeto JSON con:
- `type: "object"`
- `properties`: diccionario con 1..16 propiedades.
- `required`: lista opcional de nombres pertenecientes a `properties`.
- Claves permitidas en la raíz: exclusivamente `type`, `properties`, `required`.

Cada propiedad en la raíz puede ser:
1. **Escalar (`string`, `integer`, `number`, `boolean`)**:
   - Claves permitidas: `type`, opcionalmente `enum`, y para numéricos
     `minimum` y `maximum`.
   - `enum`: lista de 1..32 elementos únicos coincidentes con el tipo declarado.
   - `minimum` / `maximum`: números finitos, `minimum <= maximum`.
2. **`array` (profundidad 1)**:
   - Claves permitidas: `type`, `items`, opcionalmente `minItems`, `maxItems`.
   - `minItems`, `maxItems`: enteros en el rango `0..64` con `min <= max`.
   - `items`: definición de propiedad escalar o de objeto plano (1..16 escalares
     con `properties` y `required`).
3. **`object` (profundidad 1)**:
   - Claves permitidas: `type`, `properties`, opcionalmente `required`.
   - `properties`: 1..16 propiedades exclusivamente escalares.
   - Prohibido: `object` o `array` dentro de un `object` anidado (profundidad
     máxima 1).

Cualquier clave extra, tipo desconocido, recursión profunda o presencia de
`$ref`, `allOf`, `anyOf`, `oneOf`, `patternProperties` o
`additionalProperties` es rechazada en frontera con
**400 `unsupported_schema`**.

### 2.2 Validación de la Salida del Modelo (`validar_salida`)

La salida JSON del modelo se valida en frontera contra el esquema v2-ext:
1. Parseo estricto con rechazo de constantes NaN / Infinity / -Infinity.
2. Comprobación de que no falten claves de `required` y no sobren claves fuera
   de `properties` (rechazo estricto de claves extra tanto en raíz como en
   objetos anidados).
3. Verificación de tipos exactos:
   - `boolean`: sólo `bool`.
   - `integer`: `int` y `not isinstance(v, bool)`.
   - `number`: `(int, float)` y `not isinstance(v, bool)`.
   - `string`: sólo `str`.
4. Comprobación de pertenencia a `enum` y cotas `minimum <= v <= maximum`.
5. Para arrays: longitud entre `minItems` y `maxItems`, y cada elemento
   validado conforme a `items`.
6. Si alguna propiedad no cumple, se emite **502 `output_not_valid`** con
   detalle `schema_mismatch` sin propagar datos corruptos.

---

## 3. Matriz REQ-SPEC-test

| REQ | Descripción | Test Unitario |
|---|---|---|
| VX1 | `enum` escalar válido admitido en schema y validado en salida | `test_gateway_vx::test_vx1*` |
| VX2 | `minimum` / `maximum` numérico validado en schema y en salida | `test_gateway_vx::test_vx2*` |
| VX3 | `array` de escalares con `minItems`/`maxItems` validado | `test_gateway_vx::test_vx3*` |
| VX4 | `array` de objetos planos de profundidad 1 validado | `test_gateway_vx::test_vx4*` |
| VX5 | `object` anidado nivel 1 con `required` y sin claves extra | `test_gateway_vx::test_vx5*` |
| VX6 | Rechazo de recursión > 1, `$ref` o claves desconocidas | `test_gateway_vx::test_vx6*` |
| VX7 | Percepción multimodal estructurada (imagen + schema) | `test_gateway_vx::test_vx7*` |
| VX8 | Percepción multimodal estructurada (audio + schema) | `test_gateway_vx::test_vx8*` |
