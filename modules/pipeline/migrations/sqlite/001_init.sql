-- Pipeline · esquema inicial (SQLite). Portado fielmente de old_modules/m_pipeline/models.py.
-- Modelos: Pipeline (embudo configurable), PipelineStage (etapa ordenada del embudo) y
-- Deal (oportunidad que vive en una etapa y transiciona entre ellas).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Embudo de ventas configurable (p.ej. "Inbound Sales"). Compuesto de etapas ordenadas.
CREATE TABLE IF NOT EXISTS pipeline_pipeline (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_default  INTEGER NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1,
    color       TEXT NOT NULL DEFAULT '',
    "order"     INTEGER NOT NULL DEFAULT 0,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS ix_pipeline_hub_active  ON pipeline_pipeline (hub_id, is_active);
CREATE INDEX IF NOT EXISTS ix_pipeline_hub_default ON pipeline_pipeline (hub_id, is_default);
CREATE INDEX IF NOT EXISTS idx_pipeline_pipeline_hub ON pipeline_pipeline (hub_id, is_deleted);

-- Etapa dentro de un embudo (p.ej. Cualificado, Propuesta, Ganado).
-- is_won / is_lost marcan etapas terminales que auto-cierran el deal al entrar.
CREATE TABLE IF NOT EXISTS pipeline_stage (
    id                   TEXT PRIMARY KEY,
    hub_id               TEXT NOT NULL,
    pipeline_id          TEXT NOT NULL,
    code                 TEXT NOT NULL,
    name                 TEXT NOT NULL,
    "order"              INTEGER NOT NULL DEFAULT 0,
    probability_default  INTEGER NOT NULL DEFAULT 50,
    is_won               INTEGER NOT NULL DEFAULT 0,
    is_lost              INTEGER NOT NULL DEFAULT 0,
    color                TEXT NOT NULL DEFAULT '',
    is_deleted           INTEGER NOT NULL DEFAULT 0,
    deleted_at           TEXT,
    created_by           TEXT,
    updated_by           TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT,
    FOREIGN KEY (pipeline_id) REFERENCES pipeline_pipeline (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_pipeline_stage_hub_pipeline   ON pipeline_stage (hub_id, pipeline_id);
CREATE INDEX IF NOT EXISTS ix_pipeline_stage_pipeline_order ON pipeline_stage (pipeline_id, "order");
CREATE INDEX IF NOT EXISTS idx_pipeline_stage_hub           ON pipeline_stage (hub_id, is_deleted);

-- Oportunidad (deal) rastreada a través de un embudo. Vive en exactamente una etapa.
-- status: open|won|lost. won_at/lost_at se sellan al transicionar a etapa terminal.
CREATE TABLE IF NOT EXISTS pipeline_deal (
    id                   TEXT PRIMARY KEY,
    hub_id               TEXT NOT NULL,
    pipeline_id          TEXT NOT NULL,
    stage_id             TEXT NOT NULL,
    deal_name            TEXT NOT NULL,
    deal_value           NUMERIC NOT NULL DEFAULT 0,
    customer_name        TEXT NOT NULL DEFAULT '',
    expected_close_date  TEXT,                          -- ISO YYYY-MM-DD o NULL
    status               TEXT NOT NULL DEFAULT 'open',   -- open|won|lost
    entered_stage_at     TEXT,                          -- ISO datetime o NULL
    won_at               TEXT,                          -- ISO datetime o NULL
    lost_at              TEXT,                          -- ISO datetime o NULL
    lost_reason          TEXT NOT NULL DEFAULT '',
    is_deleted           INTEGER NOT NULL DEFAULT 0,
    deleted_at           TEXT,
    created_by           TEXT,
    updated_by           TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT,
    FOREIGN KEY (pipeline_id) REFERENCES pipeline_pipeline (id) ON DELETE CASCADE,
    FOREIGN KEY (stage_id)    REFERENCES pipeline_stage (id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS ix_pipeline_deal_hub_pipeline ON pipeline_deal (hub_id, pipeline_id);
CREATE INDEX IF NOT EXISTS ix_pipeline_deal_hub_stage    ON pipeline_deal (hub_id, stage_id);
CREATE INDEX IF NOT EXISTS ix_pipeline_deal_hub_status   ON pipeline_deal (hub_id, status);
CREATE INDEX IF NOT EXISTS idx_pipeline_deal_hub         ON pipeline_deal (hub_id, is_deleted);
