# ADR-003: Publicación del repositorio y licencia Apache-2.0

```text
ADR-003: Publicación del repositorio (LFM3-Omni-FK) y licencia
Apache-2.0 para el contenido; los pesos del modelo siguen en LFM Open
License v1.0
Estado: aceptado — decisión del Operador (2026-11-04); push inicial
autorizado explícitamente por operación.
Contexto: la entrada LICENSE estaba declarada pendiente desde F2
(README, decisiones de cascarón): "al decidir publicación, elegir
LICENSE y registrar la decisión". REQ-8/EV-10 fijan la licencia del
MODELO (LFM Open License v1.0, umbral comercial de 10 M USD por
entidad). El repositorio no contiene pesos: los GGUF se descargan de
Hugging Face en el primer arranque (ADR-001) y el manifiesto excluye
redistribuir el modelo o abrir servicio público sin revisión de esa
licencia.
Decisión:
  - El CONTENIDO de este repositorio (código, documentación, contratos,
    tests y scripts) se publica bajo Apache-2.0, copyright
    kristhianmanue1, en https://github.com/kristhianmanue1/LFM3-Omni-FK
    (remoto creado vacío; verificado con git ls-remote que no tenía
    historial ajeno antes del primer push).
  - Los pesos del modelo NO se relicencian ni viajan con el repo: el
    README declara la distinción código (Apache-2.0) vs modelo (LFM
    Open License v1.0) para que ningún consumidor infiera que servir el
    modelo hereda Apache-2.0. REQ-8 sigue vigente sin cambios.
  - La memoria local AN-KLA (.an-kla/) deja de versionarse en git
    (git rm --cached + .gitignore; los archivos permanecen en local).
    Razones: (1) contiene material sensible de atestación
    (.an-kla/attest.key) que no debe publicarse; (2) su estado es
    volátil (refs/CURRENT, watermarks, transacciones cambian en cada
    escritura gobernada) y versionarlo partialmente publica un store
    roto para quien clone; (3) minimización de datos del contrato
    AN-KLA.
Alternativas descartadas:
  - MIT/BSD-3: sin concesión expresa de patentes; para un servicio que
    envuelve un motor de inferencia, la cláusula de patentes de
    Apache-2.0 da mejor blindaje a los consumidores del ecosistema.
  - GPL/AGPL: contagio de licencia incompatible con el objetivo de F0
    (REQ-3: consumo por proyectos externos del ecosistema sin
    obligación de abrir su código).
  - Publicar también .an-kla: descartado por attest.key, volatilidad
    del store y minimización de datos (ver Decisión).
  - Mantener el repo privado: deja el estado v0.1.0 verificado sin
    publicar y LICENSE pendiente indefinidamente; el Operador decidió
    publicar.
Consecuencias:
  - Gana: LICENSE definida; estado publicado y auditable; términos
    claros de código para consumidores; memoria local fuera del árbol
    público.
  - Pierde: el historial de memoria AN-KLA versionado hasta 4572164
    deja de tener seguimiento (sigue en el historial de git de este
    repo para quien lo lea ahí; la continuidad futura vive solo en
    local).
  - Queda obligado: (1) nunca incluir pesos, caches del motor, logs
    (run/*.log) ni secretos en el repo; (2) cada push futuro sigue
    siendo operación extraordinaria con autorización propia (regla
    local y ADR-044 del estándar); este registro autoriza solo el push
    inicial a main; (3) sin CI ni workflows en el remoto (decisión del
    Operador: no quemar créditos).
```
