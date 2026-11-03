# Ruta de UI del ecosistema: frontExpert es la base declarada

> Regla de ruteo registrada por decisión del Operador (2026-11-02,
> adoptada el 2026-11-03). Procedencia: análisis de adopción de
> frontExpert solicitado por el Operador y verificando contra el corpus
> fuente (`/Users/krisnova/www/AGTexperts/internos/frontExpert`,
> contrato de adopción v2 en su ADR-0014). Razón: el playbook documenta
> cómo adoptarse pero no cuándo se le llama — sin esta regla registrada,
> cada encargo con UI reinventaría la respuesta.

## La regla

Todo encargo del ecosistema AGTexperts que exija **interfaz gráfica**
(web, iOS, Android) se construye sobre **frontExpert** como base de
dominio, con **skevi** como método, en adopción conjunta (patrón ya
ejecutado una vez: fase web I0–I1, issue #2 upstream).

## Qué se adoptará cuando materialice el encargo

Proyecto **nuevo separado** (nunca dentro de LFM3-Omni — su F0 excluye
paneles UI como no-objetivos), por el **contrato de adopción v2**
(ADR-0014 upstream): copiar el corpus completo salvo lo no copiable,
reescribir README/AGENTS propios, responder las 8 preguntas de
`docs/04` (cada una con default y fecha de necesidad), enmendar ADRs si
aplica, generar el manifiesto propio **como último paso**, handoff desde
plantilla, `verify-corpus.sh` en `scripts/frontexpert/` (convivencia con
los gates de skevi), rondas adversariales por fase y devolución de
lecciones por `CONTRIBUTING.md`.

## Límites de honestidad declarados (del propio corpus)

- Solo la fase **web I0–I1** fue estrenada.
- **Móvil y fases 2–6** siguen sin ejecutar: cualquier alcance móvil va
  sin red probada y exige las rondas propias.
- El stack se revalida al inicio de cada fase (`verify-stack.sh` es
  observación, no gate).

## Sinergia con este motor

AI SDK 7 (stack de frontExpert) consume APIs compatibles OpenAI — la
superficie que este proyecto publica (`lfm3-omni/superficie-inferencia
v1` en `127.0.0.1:8091/v1`) y sus tools MCP (`mcp-tools v1`). El primer
panel de control del motor o app cliente encaja en la fase 3–4 del
playbook (datos reales, agentes con efectos con `toolApproval`).

## Fuente

- Análisis de adopción solicitado por el Operador (sesión 2026-11-02).
- `README.md` y `docs/adr/0014-adopcion-externa-v2.md` de frontExpert.
- Registro permanente en memoria del ecosistema (2026-11-03).
