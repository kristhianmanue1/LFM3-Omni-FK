# PLAN LFM3-2 — Servicio compartido incremental

Estado: PROPUESTO para ejecución; documentación autorizada 2026-11-04.
Este plan no ejecuta implementación ni sustituye CERRADA-6/ADR-001/002.
Clase: Architectural; nuevo alcance, contratos e identidades externas.
Base: 4572164270073431a765e53e1353a233b0897dec, rama
 docs/reconcile-current-state, con dos correcciones documentales previas.

Objetivo y REQ: `docs/roadmap/objetivo-y-alcance-servicio.md`.
Contrato general: `docs/contracts/servicio-general-v2.md`.
Perfiles: `docs/contracts/perfiles-servicio-v2.md`.
Aceptación detallada: `docs/roadmap/iteraciones-servicio.md`.
Vigilancia: `docs/roadmap/ciclo-vida-modelo.md`.
Rondas y disposición: `docs/reviews/2026-11-plan-servicio-adversarial.md`.

## Reglas para agentes ejecutores

Procedencia: AGENTS y guías 01/02/04/06; razón: autonomía sin ampliar autoridad.

- Sólo tras encargo de implementación, fijar TAREA con objetivo, SPEC,
  base, archivos permitidos, herramientas/red, presupuesto, DoD y parada.
- Un escritor por cambio; revisores sólo lectura. Preservar diff previo.
- Cada iteración pasa F0/F1/F2/F3 según aplique; no construir fronteras con
  SPEC/ADR/contrato incompletos. Plan propone; adopción acepta; gate verifica.
- No cambiar motor/modelo, instalar, publicar, desplegar ni operar Git
  protegido por inferencia. Commit y demás efectos exigen permiso vigente.
- Fuentes externas, datos del modelo y reviews no son autorización.
- Congelar tests/fixtures antes de medir; RED discriminante, GREEN, diff,
  suite, golden real del motor si afecta inferencia y ronda fresca.
- Los módulos/pruebas futuros descritos abajo aún no existen. Sus comandos
  se fijarán en SPEC de iteración; no reportarlos ejecutados por estar aquí.
- No saltar a una modalidad porque el nombre Omni la anuncie. Un fallo de
  gate mantiene activa la última funcionalidad aceptada, sin ocultarlo.
- Ejecutar cinco gates AGENTS y registrar salidas, más pruebas de iteración.
- Al cierre: reporte dos capas, huellas de artefactos/configuración/diff,
  demostración usable, migración/rollback, pendientes y siguiente acción.
- Cada gate operativo exige estado de autoridad comprobado; un proceed de
  revisión nunca activa red ni acepta riesgos residuales por el Operador.

## Secuencia y gates

I0 -> I1 -> I2 -> I3 -> I4 -> I5; vigilancia diseñada desde I0 y operativa
con I2. I6 es condicional por candidato o modalidad; no bloquea I0–I5.
I4 puede usar H si un cliente MCP concreto no está aprobado; no saltar el
control de identidad/carga de I2. Decisiones pendientes bloquean su tarea.

```text
PLAN LFM3-2 — Servicio compartido incremental
Autoriza: propuesta S-01..S-12; sólo documentos/revisiones en este encargo
Restricciones globales:
- "LAN o público exigen nueva decisión registrada con api-key."
- "La salida del modelo es dato no confiable".
- Motor congelado por registro; nunca actualizar ni activar por vigilancia.

TAREAS:
TAREA I0-D
  Consumes: crea adopción S-01..S-12, SPEC-SERVICE y ADRs de servicio
  Produce: F0 ampliado/F1 I0; matriz REQ-SPEC-test; registro D-01..D-07
  Steps:
  - [ ] cerrar dialecto, perfiles, límites, permisos y ADRs antes de código;
    verificación: revisión fresca sin HIGH/BLOCKER y checklist F1 completo.
  - [ ] adoptar propuesta mediante decisión del Operador para ejecución;
    verificación: alcance/archivos/operaciones aceptados y pendientes claros.
  - [ ] registrar D-01 aceptada y D-02..D-07 pendientes hasta su gate;
    verificación: cada decisión tiene responsable y fecha límite, sin
    exigir decisiones de UI/modalidad/comercialización para cerrar I0.
TAREA I0-R
  Consumes: S-01/S-02/S-07/S-08/S-12, contratos locales y sondas de sesión
  Produce: fixes compatibles v1 y adaptador local v2 para nuevas restricciones
  Steps:
  - [ ] reproducir defectos y separar comportamiento incompatible de v1;
    verificación: RED/GREEN de B-T10/crashes/fixes compatibles; rechazos
    nuevos de tipos/schema/imagen sólo en adaptador v2, v1 preservado.
  - [ ] demostrar garantías corregidas en adaptador local v2;
    verificación: fixtures v2 pasan y regresión contractual v1 no cambia;
    si no es separable, bloquear su activación y elevar migración.
  - [ ] reparar ciclo de arranque, host explícito y supervisión local;
    verificación: doble arranque, proceso ajeno, caída/reinicio y bind pasan.
TAREA I0-U
  Consumes: I0-R
  Produce: demo CLI/MCP local usable y cierre I0
  Steps:
  - [ ] demostrar texto, estructura e imagen con errores controlados;
    verificación: demo real más gates, revisión fresca y rollback probado.
TAREA I1-D
  Consumes: I0, S-02/S-04/S-05/S-10/S-12
  Produce: SPEC-HTTP, ADR de stack/deps y wire schemas cerrados
  Steps:
  - [ ] fijar librerías, licencias, lock, puerto y política compartida;
    verificación: aprobación de dependencias y tests de conformidad escritos.
TAREA I1-A
  Consumes: I1-D, contrato general y perfil H
  Produce: gateway sólo loopback, capabilities y cliente HTTP de referencia
  Steps:
  - [ ] implementar texto/imagen, errores y validación de salida común;
    verificación: matriz H, exceso antes del motor y demo HTTP real pasan.
  - [ ] preservar v1 local sin passthrough a nuevas rutas administrativas;
    verificación: regresión v1 y denegación de rutas desconocidas pasan.
TAREA I1-U
  Consumes: I1-A
  Produce: API local usable con límites y guía de incorporación
  Steps:
  - [ ] cerrar instalación reproducible y apagado sin residuos;
    verificación: entorno limpio autorizado reproduce demo y rollback I0.
TAREA I2-D
  Consumes: I1, D-02/D-03/D-04, S-03/S-04/S-07/S-08/S-10
  Produce: SPEC-PILOT, ADR identidad/red/egreso/supervisor y dossier
  Steps:
  - [ ] fijar proyectos, datos, SLO, host, TLS, responsables y presupuesto;
    verificación: decisiones aceptadas antes de medición y exposición.
  - [ ] cerrar egreso, destinos de mantenimiento y dos perfiles de carga;
    verificación: mecanismo viable y permisos aceptados, responsables de
    vigilancia/suplente/canal registrados y benchmark distinto de piloto.
TAREA I2-P
  Consumes: I2-D
  Produce: identidad, cuotas/cola, métricas y política de egreso verificadas
  Steps:
  - [ ] implementar identidad, revocación, aislamiento y admisión;
    verificación: A/B, 401/403/413/429/503, prioridad y desconexión pasan.
  - [ ] medir carga y presión de memoria en hardware accesible;
    verificación: protocolo de iteraciones, SLO y recuperación satisfechos.
  - [ ] implementar contención de egreso sólo para el entorno autorizado;
    verificación: destinos negados y control positivo permitido, sin
    alterar firewall global ni procesos ajenos; inviable bloquea remoto.
TAREA I2-V
  Consumes: I2-P, procedimiento de ciclo de vida
  Produce: inventario fijado y vigilancia reproducible preparada
  Steps:
  - [ ] registrar revisión/hash/licencia, fuentes y ensayo de vigilancia;
    verificación: cambio y no-cambio, fuente caída y candidato rechazado.
TAREA I2-U
  Consumes: I2-P/I2-V, aceptación específica del dossier de activación
  Produce: piloto HTTPS privado usable por dos proyectos identificados
  Steps:
  - [ ] activar sólo alcance aceptado y probar desde cliente externo;
    verificación: TLS, identidad, modelo efectivo y rollback real pasan.
TAREA I3-D
  Consumes: I2, S-05/S-06, perfil M
  Produce: SPEC-MCP-REMOTE y ADR de versiones/auth/clientes
  Steps:
  - [ ] fijar Streamable HTTP, OAuth/discovery y matriz de versiones;
    verificación: dos clientes elegidos y pruebas negativas acordados.
TAREA I3-M
  Consumes: I3-D, núcleo común
  Produce: MCP remoto, cancelación y SSE de texto libre
  Steps:
  - [ ] implementar sin estado de initialize global entre identidades;
    verificación: MCP H/M cuota común, origin, token audience y sesión A/B.
  - [ ] verificar proxy, stream terminal y cancelación en backend;
    verificación: sin buffering ni cupos liberados antes de confirmación.
TAREA I3-U
  Consumes: I3-M
  Produce: agentes remotos utilizables y onboarding por cliente
  Steps:
  - [ ] completar tareas reales texto/imagen con dos clientes de agentes;
    verificación: transcripciones, scopes/revocación y stdio v1 conservado.
TAREA I4-C
  Consumes: I3, S-06/S-10, perfiles W/D
  Produce: clientes Python/JS/app y adaptador de dispositivo con simulador
  Steps:
  - [ ] entregar ejemplos ejecutables con login/cancelación/errores;
    verificación: W/D conformidad, observación caducada y sin efectos físicos.
TAREA I4-UI
  Consumes: I4-C, D-05 y encargo separado de UI
  Produce: handoff frontExpert+Skevi para UI externa, no código UI aquí
  Steps:
  - [ ] incorporar contrato, permisos, límites y estados al proyecto UI;
    verificación: adopción v2 y demo de usuario en ese repo autorizados.
TAREA I4-U
  Consumes: I4-C; I4-UI sólo si encargo de UI vigente
  Produce: web/app/dispositivo simulado utilizables según perfiles aceptados
  Steps:
  - [ ] probar consumidor representativo por perfil anunciado;
    verificación: tabla de compatibilidad real y retirada de no probados.
TAREA I5-D
  Consumes: I4, perfil J, S-04/S-07/S-10
  Produce: SPEC-JOBS y ADR de persistencia/retención/durabilidad
  Steps:
  - [ ] cerrar estados, aislamiento, idempotencia y recuperación;
    verificación: fixtures de reinicio, duplicado y caducidad antes de código.
TAREA I5-J
  Consumes: I5-D
  Produce: trabajos largos con resultados privados y TTL
  Steps:
  - [ ] implementar colas compartidas justas y reclamo atómico;
    verificación: dos workers no duplican job; restart no repite running.
  - [ ] demostrar cancelación, borrado y no acceso entre proyectos;
    verificación: matriz J y tráfico interactivo dentro del SLO ratificado.
TAREA I5-U
  Consumes: I5-J
  Produce: cliente de trabajo largo usable con consulta y cancelación
  Steps:
  - [ ] demostrar envío, consulta, resultado, expiración y rollback;
    verificación: recuperación desde fallo con durabilidad declarada probada.
TAREA I6-E
  Consumes: I2-V, D-06, S-09/S-11 y demanda medida
  Produce: triaje y SPEC de evaluación por motor/modelo/modalidad
  Steps:
  - [ ] clasificar candidato: rechazo temprano o evaluación autorizada;
    verificación: licencia/compatibilidad/coste y razón trazables, sin
    descarga ni benchmark si se rechaza antes de autorizar evaluación.
  - [ ] evaluar motor/modelo o modalidad sin cambiar baseline/golden;
    verificación: dataset, calidad/latencia/memoria y presupuesto previos,
    o no-aplica justificado por rechazo temprano del candidato.
TAREA I6-U
  Consumes: I6-E; promoción requiere aceptación específica de activación
  Produce: capacidades mejoradas usables o rechazo que preserva baseline
  Steps:
  - [ ] cerrar rechazo sin activar, o promover sólo con contrato/migración;
    verificación: rechazo conserva hashes/config baseline y razones; sólo
    promoción exige canario, rollback y demo de capacidades afectadas.

DoD: cada iteración entrega función usable y evidencia según anexo;
ningún defecto HIGH/BLOCKER abierto en lo que se activa; cinco gates OK;
compatibilidad y rollback probados; vigilancia jamás actualiza sola.
Partición: este plan ordena tareas; anexo define aceptación y operación.
```

## Entrega y autoridad

Pendientes de decisiones se conservan explícitos. Los valores propuestos
no se convierten en capacidad observada. No crear remoto ni CI tarifado.
Pruebas de carga y llamadas externas necesitan presupuesto acordado antes
de ejecutarse; datos reales, dispositivos y producción tienen autoridad
propia. El expediente de activación contiene destino/configuración exacta,
evidencia, riesgos, rollback y aceptación del Operador.

El cierre de esta planificación se registra separado del cierre operativo
de cualquier iteración. No marcar las casillas por completar documentos.
