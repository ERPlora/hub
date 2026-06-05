-- Workflows · esquema inicial (SQLite). Portado fielmente de old_modules/m_workflows/models.py.
-- Motor de automatización: un Workflow define un disparador (manual / scheduled / event /
-- webhook) + condiciones + acciones; cada ejecución crea un WorkflowRun y un WorkflowStep
-- por acción. Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.
-- Las columnas JSON del legacy (trigger_config, conditions, actions, params, result,
-- input_data, output_data) se almacenan como TEXT con JSON serializado.

-- Definición de automatización: disparador + condiciones + acciones.
CREATE TABLE IF NOT EXISTS workflows_workflow (
    id             TEXT PRIMARY KEY,
    hub_id         TEXT NOT NULL,
    name           TEXT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    trigger_type   TEXT NOT NULL DEFAULT 'manual',  -- manual|scheduled|event|webhook
    trigger_config TEXT NOT NULL DEFAULT '{}',       -- JSON con config del disparador
    conditions     TEXT NOT NULL DEFAULT '[]',       -- JSON lista de condiciones {field,op,value}
    actions        TEXT NOT NULL DEFAULT '[]',       -- JSON lista de acciones {type,params}
    is_active      INTEGER NOT NULL DEFAULT 0,
    last_run_at    TEXT,                              -- ISO datetime o NULL
    total_runs     INTEGER NOT NULL DEFAULT 0,
    is_deleted     INTEGER NOT NULL DEFAULT 0,
    deleted_at     TEXT,
    created_by     TEXT,
    updated_by     TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT
);
CREATE INDEX IF NOT EXISTS ix_wf_hub_active   ON workflows_workflow (hub_id, is_active);
CREATE INDEX IF NOT EXISTS ix_wf_hub_trigger  ON workflows_workflow (hub_id, trigger_type);
CREATE INDEX IF NOT EXISTS idx_workflows_workflow_hub ON workflows_workflow (hub_id, is_deleted);

-- Una ejecución de un workflow.
CREATE TABLE IF NOT EXISTS workflows_run (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    workflow_id   TEXT NOT NULL,
    started_at    TEXT,                          -- ISO datetime o NULL
    completed_at  TEXT,                          -- ISO datetime o NULL
    status        TEXT NOT NULL DEFAULT 'running', -- running|completed|failed|cancelled
    input_data    TEXT NOT NULL DEFAULT '{}',     -- JSON contexto de entrada
    output_data   TEXT NOT NULL DEFAULT '{}',     -- JSON resultado de la ejecución
    error_message TEXT NOT NULL DEFAULT '',
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT,
    FOREIGN KEY (workflow_id) REFERENCES workflows_workflow (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_wfr_hub_workflow ON workflows_run (hub_id, workflow_id);
CREATE INDEX IF NOT EXISTS ix_wfr_hub_status   ON workflows_run (hub_id, status);
CREATE INDEX IF NOT EXISTS idx_workflows_run_hub ON workflows_run (hub_id, is_deleted);

-- Una acción dentro de una ejecución (paso ordenado).
CREATE TABLE IF NOT EXISTS workflows_step (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    run_id        TEXT NOT NULL,
    step_order    INTEGER NOT NULL DEFAULT 0,
    step_type     TEXT NOT NULL,
    params        TEXT NOT NULL DEFAULT '{}',     -- JSON parámetros de la acción
    result        TEXT NOT NULL DEFAULT '{}',     -- JSON resultado del paso
    status        TEXT NOT NULL DEFAULT 'pending', -- pending|running|done|failed|skipped
    started_at    TEXT,                          -- ISO datetime o NULL
    completed_at  TEXT,                          -- ISO datetime o NULL
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT,
    FOREIGN KEY (run_id) REFERENCES workflows_run (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_wfs_hub_run ON workflows_step (hub_id, run_id);
CREATE INDEX IF NOT EXISTS idx_workflows_step_hub ON workflows_step (hub_id, is_deleted);
