# ai_agents — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_ai_agents/{models.py,services.py}`. El CRUD plano de agentes
(crear/actualizar/desactivar) y los listados ya están en SQL declarativo Tier 0
(`commands/*.sql`, `queries/*.sql`). Lo que sigue es el **ciclo de vida de los runs**:
numeración atómica, secuenciación de pasos y agregación de métricas que **no** cabe en
una sola sentencia SQL y debe convertirse en handler WASM (`handler/src/lib.rs` →
`dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar) que el runtime
> valida y persiste en una transacción. Importes monetarios como decimales con
> `quantize(0.0001)` (la columna es `NUMERIC(15,4)` en legacy).

## 1. `start_run`  (command `ai_agents.runs.start`)
Origen: `AgentService.start_run` + `AgentService._next_run_number`.
- Validar `trigger_type ∈ {manual, scheduled, event}` (ya lo cubre el schema; revalidar).
- Cargar el `Agent` por `agent_id` (lectura mediada por el runtime). Si no existe → error
  `agent_not_found`. Si `is_active == 0` → error `agent_inactive`.
- **Numeración atómica** `AGR-YYYYMMDD-NNNN`:
  - `prefix = "AGR-{today}-"` con `today = UTC YYYYMMDD` (capacidad de "reloj" del host).
  - `NNNN` = secuencia por `(hub_id, día)`, 4 dígitos, sin ventana SELECT→INSERT
    (en hub-next se resuelve como counter UPSERT del runtime, igual que `quotes`).
  - El WASM solo formatea `AGR-{day}-{n:04d}` con el número devuelto por el counter.
- Insertar `ai_agents_run` con `status='queued'`, `trigger_type`, `input_query`,
  `iterations_used=0`, `tokens_used=0`, `cost_eur=0`.
- Emitir `ai_agents.run.started`. Devolver `{id, run_number, agent_id, status}`.

## 2. `record_step`  (command `ai_agents.runs.record_step`)
Origen: `AgentService.record_step`.
- Validar `step_type ∈ {thought, tool_call, observation, answer}` (schema; revalidar).
- Cargar el `AgentRun` por `run_id`. Si no existe → error `run_not_found`.
- **Guarda de estado**: si `status ∈ {completed, failed, timeout}` → error `invalid_state`
  ("Cannot record steps on a <status> run.").
- **Secuenciación de pasos**: `next_index = max(step_index actuales del run, default -1) + 1`
  (requiere leer los pasos existentes del run → no es una sola sentencia).
- Insertar `ai_agents_step` con `run_id`, `step_index=next_index`, `step_type`, `tool_name`,
  `content`, `tokens_used`, `occurred_at = now()` (reloj del host).
- **Actualizar el run en el mismo paso**:
  - Si `status == 'queued'` → `status='running'` y `started_at = now()`.
  - `iterations_used = next_index + 1`.
  - `tokens_used = tokens_used + tokens_used(paso)`.
- Emitir `ai_agents.run.step_recorded`. Devolver `{id, run_id, step_index, step_type}`.

## 3. `complete_run`  (command `ai_agents.runs.complete`)
Origen: `AgentService.complete_run`.
- Cargar `AgentRun`. Si no existe → error `run_not_found`.
- **Guarda de estado**: si `status ∈ {completed, failed, timeout}` → error `invalid_state`.
- Parsear `cost_eur` (string decimal). Si no es decimal válido → error `invalid_cost`.
- Cargar el `Agent` dueño (`run.agent_id`). Si no existe → error `agent_not_found`.
- **Mutación atómica sobre run + agent** (dos filas, dos tablas — por eso es WASM):
  - run: `status='completed'`, `final_output`, `completed_at = now()`,
    `tokens_used = tokens_used + tokens_used(payload)`,
    `cost_eur = cost_eur + cost(payload)`.
  - agent (métricas acumuladas denormalizadas): `total_runs = total_runs + 1`,
    `total_cost_eur = total_cost_eur + run.cost_eur` (el nuevo total del run, ya incrementado).
- Emitir `ai_agents.run.completed`. Devolver `{id, run_number, status, tokens_used, cost_eur}`.

## 4. `fail_run`  (command `ai_agents.runs.fail`)
Origen: `AgentService.fail_run`.
- Cargar `AgentRun`. Si no existe → error `run_not_found`.
- **Guarda de estado**: si `status ∈ {completed, failed, timeout}` → error `invalid_state`.
- Cargar el `Agent` dueño. Si no existe → error `agent_not_found`.
- **Mutación atómica sobre run + agent**:
  - run: `status='failed'`, `error_message`, `completed_at = now()`.
  - agent: `total_runs = total_runs + 1` (NO toca `total_cost_eur` — el run falló).
- Emitir `ai_agents.run.failed`. Devolver `{id, run_number, status, error_message}`.

## 5. `get_agent_metrics`  (NO migrado todavía — agregación de solo lectura)
Origen: `AgentService.get_agent_metrics`.
- No es un command mutante: es un cálculo de agregados sobre los runs de un agente en los
  últimos `period_days` (total / completed / failed / timeout / running / queued, success_rate,
  total_tokens, total_cost_eur) + las métricas lifetime del agente.
- Opciones de implementación:
  - **A (preferida):** query Tier 0 con `GROUP BY status` + `SUM(tokens_used)` /
    `SUM(cost_eur)` filtrando `created_at >= :since`, y el SDK/UI compone `success_rate`
    y mezcla las métricas lifetime (`total_runs`, `total_cost_eur`) del agente. Si se hace
    así, añadir una query `ai_agents.agents.metrics` a `module.json` (NO se ha añadido aún:
    sin SQL no se declara, para no dejar paths colgantes).
  - **B:** handler WASM de solo lectura que recibe las filas y devuelve el dict de métricas
    (replica exacta de `get_agent_metrics`, incluido `round(success_rate, 4)`).
- `period_days < 1` → error `invalid_period_days`.

## Notas de portabilidad
- `tools` se serializa como JSON (`TEXT`) en SQLite; en Postgres puede ir como `jsonb`.
  El WASM trata `tools` como lista de strings (saneo: descartar vacíos, `str()` cada item),
  igual que `create_agent`/`update_agent` legacy.
- Todas las marcas de tiempo (`started_at`, `completed_at`, `occurred_at`, `created_at`,
  `updated_at`) las pone el runtime/host en ISO-8601 UTC; el WASM no inventa relojes.
