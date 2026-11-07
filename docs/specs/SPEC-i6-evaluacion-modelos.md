# SPEC-i6-evaluacion-modelos: Protocolo de triaje, evaluación comparativa y promoción/rechazo de motor, modelo y modalidades

- **Fase**: I6 (Fase 6 del PLAN LFM3-2: Servicio Compartido)
- **Estado**: Aceptado / En implementación
- **Procedencia**: I2-V, D-06, S-09, S-11, ADR-001, ADR-008, `ciclo-vida-modelo.md`
- **Fecha**: 2026-11-07
- **Autoridad**: Decisión del Operador (sesión 2026-11-07)

---

## 1. Contexto y Principio de Motor Congelado

El estándar de diseño y las decisiones del proyecto (D-06, ADR-001) establecen
que el motor `llama.cpp` y el modelo `LiquidAI/LFM3-Omni-2B-GGUF` están **congelados
por registro**. La vigilancia periódica (I2-V) detecta nuevas versiones o
candidatos en las fuentes oficiales, pero:

> [!IMPORTANT]
> **Prohibición de actualización silenciosa**: Ningún componente de inferencia
> se actualiza, descarga o sustituye automáticamente en producción. Cualquier
> cambio de motor o pesos es una operación gobernada y registrada que exige
> triaje previo, evaluación comparativa sin alterar el baseline, y autorización
> explícita del Operador.

---

## 2. Compuerta de Rechazo Temprano (Early Rejection Gate)

Antes de autorizar la descarga de artefactos pesados o ejecutar benchmarks que
consuman recursos del host, todo candidato detectado debe superar un triaje
automático de metadatos (`triaged` $\to$ `rejected` o `evaluation_authorized`):

1. **Licencia y gobernanza**:
   - La licencia debe ser permisiva o admisible para el entorno local de
     AGTexperts (LFM Open License v1.0, Apache-2.0, MIT o equivalente).
   - Licencias con cláusulas de telemetría obligatoria, prohibición de uso
     comercial o restricciones de hosting son **rechazadas de inmediato**.
2. **Compatibilidad de arquitectura y hardware**:
   - El artefacto debe ser ejecutable sobre el runtime `llama.cpp` congelado en
     el host (Apple Silicon / Metal / CPU x86_64 / WSL).
   - Candidatos que exijan drivers propietarios no disponibles o dependencias
     externas pesadas quedan descartados.
3. **Presupuesto de memoria y contención**:
   - La memoria requerida para el contexto de trabajo no debe superar el
     presupuesto físico asignado (RSS pico $\le 6\text{ GB}$).
   - Cualquier requerimiento que fuerce swapping global en el host es motivo
     de rechazo temprano.
4. **Cobertura omnimodal integral**:
   - Salvo encargo de un modelo especializado para una única modalidad,
     cualquier reemplazo general del motor debe soportar o superar las cinco
     modalidades activas: texto estructurado, visión, audio, voz y video.

---

## 3. Protocolo de Evaluación Comparativa (Golden Dataset)

Para candidatos que superen el triaje temprano y cuenten con autorización:

### 3.1 Conjunto Dorado de Pruebas (Golden Dataset)

El candidato se evalúa contra un banco de pruebas representativo sin alterar los
archivos ni el servicio activo del baseline:

| ID Prueba | Modalidad | Entrada de Prueba | Criterio de Éxito |
|---|---|---|---|
| **GOLD-01** | Texto estructurado | Inferencia con esquema `schema v2-ext` | 100% conformidad con esquema JSON |
| **GOLD-02** | Percepción visual | Imagen sintética / fotograma con OCR | Precisión en reconocimiento visual |
| **GOLD-03** | Audio (ASR) | Audio WAV 16 kHz de referencia | Coeficiente WER $\le$ baseline |
| **GOLD-04** | Voz (TTS) | Síntesis de voz hablada en español | Exclusión mutua limpia y audio válido |
| **GOLD-05** | Video corto | MP4 corto ($\le 5\text{ s}$) | Detección temporal coherente |

### 3.2 Dimensiones Métricas Evaluadas

1. **Calidad**: Tasa de errores sintácticos o alucinaciones frente al golden dataset.
2. **Latencia**: Comparación de percentiles p50 y p95 Time-To-First-Token (TTFT)
   y tiempo total de procesamiento por turno.
3. **Memoria**: Monitoreo de RSS pico durante la inferencia y liberación limpia
   al terminar el turno.
4. **Estabilidad**: Cero fugas de descriptores de archivo o procesos zombies.

---

## 4. Protocolo de Veredicto y Cierre

### 4.1 Veredicto por Defecto: Rechazo Formal (Fail-Closed)

Si el candidato:
- Obtiene un rendimiento inferior al baseline en calidad o latencia.
- Incrementa el uso de memoria en más de un 10%.
- Presenta inestabilidad o defectos en alguna modalidad activa.

Se emite un **Dictamen Formal de Rechazo**:
- El candidato transiciona a estado `rejected`.
- Se registra inmutablemente el motivo y la evidencia técnica.
- **El baseline activo, sus hashes SHA-256 y su configuración permanecen intactos**.

### 4.2 Veredicto por Promoción (Excepcional y Gobernado)

Solo si el candidato supera demostrablemente al baseline en todas las métricas
clave y el Operador autoriza la migración:
1. Se publica propuesta formal de promoción (`promotion_proposed`).
2. Se ejecuta despliegue canario en puerto secundario (sin sustituir el puerto principal).
3. Se verifica el procedimiento de **rollback inmediato en un solo paso**
   para garantizar reversibilidad instantánea en caso de anomalía.
4. Una vez validado en canario, se promueve a activo actualizando los registros
   de inventario congelado.

---

## 5. Criterios de Aceptación

1. Existencia del evaluador automatizado en `src/evaluacion_modelos.py`.
2. Verificación en pruebas unitarias de los caminos de rechazo temprano
   (licencia, arquitectura, memoria) y evaluación comparativa.
3. Verificación de la preservación estricta del baseline congelado.
4. Cumplimiento de los 5 gates Skevi y reporte adversarial registrado.
