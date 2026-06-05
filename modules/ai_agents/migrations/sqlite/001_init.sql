-- AI Agents · esquema inicial (SQLite). Portado fielmente de old_modules/m_ai_agents/models.py.
-- Modelos: Agent (definición: prompt + tools + config), AgentRun (una ejecución, con
-- estado y contabilidad de tokens/coste) y AgentStep (traza paso a paso de un run).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Agente: definición de un agente autónomo (system_prompt + lista de tools permitidas).
-- code es único por hub. tools se guarda como JSON (lista de nombres de acciones).
-- total_runs / total_cost_eur son métricas acumuladas denormalizadas (las mantiene el runtime).
CREATE TABLE IF NOT EXISTS ai_agents_agent (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    code             TEXT NOT NULL,
    name             TEXT NOT NULL,
    description      TEXT NOT NULL DEFAULT '',
    agent_type       TEXT NOT NULL DEFAULT 'assistant',  -- assistant|automation|monitor|analyzer
    system_prompt    TEXT NOT NULL DEFAULT '',
    tools            TEXT NOT NULL DEFAULT '[]',          -- JSON: lista de nombres de tools/acciones
    max_iterations   INTEGER NOT NULL DEFAULT 10,
    model_preference TEXT NOT NULL DEFAULT '',
    is_active        INTEGER NOT NULL DEFAULT 1,
    total_runs       INTEGER NOT NULL DEFAULT 0,
    total_cost_eur   NUMERIC NOT NULL DEFAULT 0,
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_ai_agents_hub_code   ON ai_agents_agent (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_ai_agents_hub_active  ON ai_agents_agent (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS ix_ai_agents_hub_type    ON ai_agents_agent (hub_id, agent_type);
CREATE INDEX        IF NOT EXISTS idx_ai_agents_agent_hub  ON ai_agents_agent (hub_id, is_deleted);

-- Ejecución de un agente: ciclo de vida completo (queued→running→completed/failed/timeout).
-- run_number es único por hub con formato AGR-YYYYMMDD-NNNN (lo genera el runtime — ver WASM-TODO).
-- iterations_used / tokens_used / cost_eur son contabilidad acumulada del run.
CREATE TABLE IF NOT EXISTS ai_agents_run (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    run_number      TEXT NOT NULL,
    agent_id        TEXT NOT NULL,
    trigger_type    TEXT NOT NULL DEFAULT 'manual',   -- manual|scheduled|event
    input_query     TEXT NOT NULL DEFAULT '',
    final_output    TEXT NOT NULL DEFAULT '',
    error_message   TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'queued',   -- queued|running|completed|failed|timeout
    iterations_used INTEGER NOT NULL DEFAULT 0,
    tokens_used     INTEGER NOT NULL DEFAULT 0,
    cost_eur        NUMERIC NOT NULL DEFAULT 0,
    started_at      TEXT,
    completed_at    TEXT,
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    FOREIGN KEY (agent_id) REFERENCES ai_agents_agent (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_ai_agents_run_hub_number ON ai_agents_run (hub_id, run_number);
CREATE INDEX        IF NOT EXISTS ix_ai_agents_run_hub_agent  ON ai_agents_run (hub_id, agent_id);
CREATE INDEX        IF NOT EXISTS ix_ai_agents_run_hub_status ON ai_agents_run (hub_id, status);
CREATE INDEX        IF NOT EXISTS idx_ai_agents_run_hub       ON ai_agents_run (hub_id, is_deleted);

-- Paso de un run: thought / tool_call / observation / answer. step_index es secuencial por run.
-- tool_name solo aplica cuando step_type = 'tool_call'. tokens_used = tokens de ESTE paso.
CREATE TABLE IF NOT EXISTS ai_agents_step (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    run_id      TEXT NOT NULL,
    step_index  INTEGER NOT NULL,
    step_type   TEXT NOT NULL,                 -- thought|tool_call|observation|answer
    tool_name   TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL DEFAULT '',
    tokens_used INTEGER NOT NULL DEFAULT 0,
    occurred_at TEXT,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT,
    FOREIGN KEY (run_id) REFERENCES ai_agents_run (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_ai_agents_step_run      ON ai_agents_step (run_id, step_index);
CREATE INDEX IF NOT EXISTS idx_ai_agents_step_hub     ON ai_agents_step (hub_id, is_deleted);
