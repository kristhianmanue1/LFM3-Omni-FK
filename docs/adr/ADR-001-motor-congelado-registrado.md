# ADR-001: Motor de inferencia congelado por registro

```text
ADR-001: Motor de inferencia congelado por registro (llama.cpp 0.8.0
b11960 + LFM3-Omni-2B GGUF Q4_K_M)
Estado: aceptado — implementado en F0 (evidencia EV-9; batería B-T1..B-T9)
Contexto: REQ-1 (servir el modelo), REQ-2 (puerto 8091), REQ-5 (M2 Air
16 GB), REQ-6 (greedy, no-reasoning). Evidencia de F0: EV-4..EV-6, EV-9;
capacidades medidas en docs/verificaciones-motor.md. El modelo exige
llama.cpp >= v0.8.0 (b11960); Homebrew distribuye exactamente 0.8.0
bottled (EV-5).
Decisión: el motor es llama.cpp instalado por Homebrew (versión 0.8.0,
build 11960) y los pesos son LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M con su
mmproj automático; ambos viven fuera del repositorio y no se editan en
sitio: la pareja versión+build+modelo queda fijada por este registro y
cualquier salto es una operación registrada con re-batería del golden
set (régimen de árbol congelado por registro, plantilla frozen-trees
no aplicada por no haber árbol dentro del repo).
Alternativas descartadas:
  - Docker Model Runner / imagen llama.cpp en contenedor: añade una capa
    de red y de Docker innecesaria para un servicio de localhost (la
    máquina ya tiene un contenedor ajeno ocupando el 8080, EV-3) y
    complica el runbook sin beneficio para REQ-5.
  - Ollama: intermedia el runtime y gestiona su propio almacén de
    modelos; el control fino del runbook (reasoning off, temp 0, puerto,
    mmproj) queda atado a lo que Ollama exponga y a su calendario de
    soporte omni; llama.cpp es el runtime de referencia de la ficha
    oficial del modelo.
  - Build desde fuente: control total sin beneficio observable: la
    versión bottled es exactamente la revisión mínima que el modelo
    exige; el costo de mantenimiento no se justifica (desempate del
    estándar: más simple).
Consecuencias:
  - Gana: runbook reproducible (F0 §7), capacidades medidas y
    contractuales (B-T1..B-T9), dependencia mínima (Homebrew).
  - Pierde: actualizaciones de motor y modelo exigen registro y
    re-verificación; no hay parcheo local del motor.
  - Queda obligado: la pareja llama.cpp 0.8.0 b11960 + Q4_K_M es la
    declarada en el CONTRATO lfm3-omni/superficie-inferencia v1; cambiar
    cualquiera de los dos es incompatible y exige v2 del contrato.
  - La licencia del modelo es lfm1.0 (EV-10): consumo interno del
    ecosistema dentro del umbral; cualquier esquema de cobro a terceros
    documenta y mantiene el umbral (REQ-8).
```
