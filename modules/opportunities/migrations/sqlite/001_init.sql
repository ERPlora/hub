-- Opportunities · esquema inicial (SQLite). Portado fielmente de old_modules/m_opportunities/models.py.
-- CRM sales pipeline: Opportunity (oportunidad de venta por etapas), OpportunityActivity
-- (registro de interacciones call/email/meeting/note) y OpportunityCounter (secuencia
-- atómica por hub+día para el número OPP-YYYYMMDD-NNNN).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Oportunidad de venta moviéndose por el pipeline.
-- opp_number es único por hub (lo garantiza el índice ix_opp_hub_number).
-- stage ∈ prospecting|qualification|proposal|negotiation|won|lost.
-- probability 0–100; value en decimal; weighted_value = value * probability/100 (lo calcula WASM).
CREATE TABLE IF NOT EXISTS opportunities_opportunity (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    opp_number          TEXT NOT NULL,
    customer_name       TEXT NOT NULL,
    customer_email      TEXT NOT NULL DEFAULT '',
    value               NUMERIC NOT NULL DEFAULT 0,
    probability         INTEGER NOT NULL DEFAULT 0,        -- 0–100
    expected_close_date TEXT,                              -- ISO YYYY-MM-DD o NULL
    stage               TEXT NOT NULL DEFAULT 'prospecting',
    close_reason        TEXT NOT NULL DEFAULT '',
    assigned_to_ref     TEXT,                              -- UUID de usuario o NULL
    notes               TEXT NOT NULL DEFAULT '',
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_opp_hub_number      ON opportunities_opportunity (hub_id, opp_number);
CREATE INDEX        IF NOT EXISTS ix_opp_hub_stage       ON opportunities_opportunity (hub_id, stage);
CREATE INDEX        IF NOT EXISTS ix_opp_hub_assigned    ON opportunities_opportunity (hub_id, assigned_to_ref);
CREATE INDEX        IF NOT EXISTS ix_opp_hub_close_date  ON opportunities_opportunity (hub_id, expected_close_date);
CREATE INDEX        IF NOT EXISTS idx_opportunities_opportunity_hub ON opportunities_opportunity (hub_id, is_deleted);

-- Interacción registrada (call/email/meeting/note) sobre una oportunidad.
-- Si scheduled_for es NULL la actividad se registra como ya completada (completed_at).
CREATE TABLE IF NOT EXISTS opportunities_activity (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    opportunity_id    TEXT NOT NULL,
    activity_type     TEXT NOT NULL,                       -- call|email|meeting|note
    description       TEXT NOT NULL DEFAULT '',
    scheduled_for     TEXT,                                -- ISO datetime o NULL
    completed_at      TEXT,                                -- ISO datetime o NULL
    completed_by_ref  TEXT,                                -- UUID de usuario o NULL
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    FOREIGN KEY (opportunity_id) REFERENCES opportunities_opportunity (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_opp_activity_opp           ON opportunities_activity (opportunity_id);
CREATE INDEX IF NOT EXISTS ix_opp_activity_hub_type      ON opportunities_activity (hub_id, activity_type);
CREATE INDEX IF NOT EXISTS idx_opportunities_activity_hub ON opportunities_activity (hub_id, is_deleted);

-- Contador atómico por (hub, día) para generar opp_number sin carrera SELECT→UPDATE.
-- El runtime lo incrementa vía UPSERT (INSERT ... ON CONFLICT DO UPDATE ... RETURNING).
-- day = 'YYYYMMDD'. Ver WASM-TODO (generate_opp_number).
CREATE TABLE IF NOT EXISTS opportunities_counter (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    day          TEXT NOT NULL,                            -- YYYYMMDD
    last_number  INTEGER NOT NULL DEFAULT 0,
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_opp_counter_hub_day  ON opportunities_counter (hub_id, day);
CREATE INDEX        IF NOT EXISTS idx_opportunities_counter_hub ON opportunities_counter (hub_id, is_deleted);
