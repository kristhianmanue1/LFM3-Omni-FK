# ADR-004: Estrategia de validación en frontera del adaptador local v2

```text
ADR-004: Validación de frontera del adaptador v2 con validador propio
en stdlib y dialecto cerrado
Estado: aceptado (I0-D; encargo del Operador, 2026-11-04)
Contexto: I0 exige rechazos nuevos (campos desconocidos, dialecto de
schema, imágenes inválidas, URLs externas) SIN estrechar v1: la salida
es el adaptador local v2 (PLAN LFM3-2, TAREA I0-R). Las sondas de la
planificación confirmaron que el motor ignora campos y esquemas que no
soporta (objetivo-y-alcance, §Estado de partida). La guía 06 §5 exige
validar la salida del modelo en frontera. La elección de librería de
validación debe comparar al menos dos alternativas con licencia y
superficie (objetivo-y-alcance, §Decisiones pendientes).
Decisión: el adaptador v2 valida con un validador propio en Python
stdlib (3.12+; piso fijado por el Operador el mismo día), contra un
dialecto cerrado declarado en el SPEC I0, no
contra JSON Schema completo. El dialecto declara lo que SÍ se verifica
(tipos primitivos, required, cotas de tamaño y píxeles) y lo que NO se
soporta (anidación, additionalProperties, referencias, streaming); lo
no soportado se rechaza con error estructurado en vez de prometerlo en
silencio. Sin dependencias nuevas: continúa la decisión de cascarón
(README §Decisiones de cascarón) y no hay autorización vigente de
instalación. Alternativas descartadas:
  - jsonschema (PyPI, MIT): valida el borrador completo de JSON Schema,
    pero exige instalar una dependencia sin autoridad específica,
    añadir lockfile y revertir el registro de cascarón; para el
    dialecto cerrado de I0 su potencia sobra y su superficie de ataque
    (documentos arbitrarios) no se necesita.
  - fastjson / validadores C: mismo costo de dependencia más compilación
    por plataforma; incompatible con el requisito de reproducibilidad
    local sin build.
Consecuencias:
  - Gana: cero dependencias; dialecto auditable línea a línea; rechazo
    honesto de lo no soportado (fail-closed, guía 06 §5); un solo
    runtime (python3.12+).
  - Pierde: no se validan rasgos avanzados de JSON Schema ($ref,
    patternProperties, oneOf); ampliar el dialecto exige editar el
    validador y su SPEC, no configurar una librería.
  - Queda obligado: el adaptador nunca reenvía al motor nada que no
    pasó su frontera; el dialecto declarado en el SPEC es la única
    fuente de qué se verifica; cualquier cambio de dialecto es cambio
    de SPEC con RED/GREEN propio. I1 podrá revisar esta elección con
    su ADR propio si su alcance lo justifica.
```
