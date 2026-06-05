-- Cash Flow Forecasting · esquema inicial (SQLite). Portado fielmente de
-- old_modules/m_cashflow_forecasting/models.py.
-- Modelos: CashflowScenario (configuración de escenario), CashflowProjection
-- (una ejecución de proyección sobre un rango de periodos) y ProjectionPoint
-- (punto por periodo con entradas/salidas y saldos).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Escenario de cash-flow: tipo + saldo inicial + parámetros libres (JSON).
-- code es único por hub y es el identificador estable referenciado por el resto.
-- scenario_type: baseline|optimistic|pessimistic|custom.
CREATE TABLE IF NOT EXISTS cashflow_forecasting_scenario (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    code            TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    scenario_type   TEXT NOT NULL DEFAULT 'baseline',  -- baseline|optimistic|pessimistic|custom
    opening_balance NUMERIC NOT NULL DEFAULT 0,
    currency        TEXT NOT NULL DEFAULT 'EUR',
    is_active       INTEGER NOT NULL DEFAULT 1,
    parameters      TEXT NOT NULL DEFAULT '{}',        -- JSON de parámetros del escenario
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_cf_scenario_hub_code   ON cashflow_forecasting_scenario (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_cf_scenario_hub_active ON cashflow_forecasting_scenario (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS ix_cf_scenario_hub_type   ON cashflow_forecasting_scenario (hub_id, scenario_type);
CREATE INDEX        IF NOT EXISTS idx_cashflow_forecasting_scenario_hub ON cashflow_forecasting_scenario (hub_id, is_deleted);

-- Proyección: una ejecución de cálculo para un escenario sobre un rango de fechas.
-- projection_number es legible (CFP-YYYYMMDD-NNNN). status: running|completed|failed.
-- period_unit: day|week|month. La generación de puntos la hace el handler WASM.
CREATE TABLE IF NOT EXISTS cashflow_forecasting_projection (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    scenario_id       TEXT NOT NULL,
    projection_number TEXT NOT NULL,
    period_start      TEXT NOT NULL,                  -- ISO YYYY-MM-DD
    period_end        TEXT NOT NULL,                  -- ISO YYYY-MM-DD
    period_unit       TEXT NOT NULL DEFAULT 'month',  -- day|week|month
    generated_at      TEXT,                           -- ISO datetime o NULL
    generated_by_ref  TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'running',-- running|completed|failed
    notes             TEXT NOT NULL DEFAULT '',
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    FOREIGN KEY (scenario_id) REFERENCES cashflow_forecasting_scenario (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_cf_projection_hub_status    ON cashflow_forecasting_projection (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_cf_projection_hub_scenario  ON cashflow_forecasting_projection (hub_id, scenario_id);
CREATE INDEX IF NOT EXISTS ix_cf_projection_hub_generated ON cashflow_forecasting_projection (hub_id, generated_at);
CREATE INDEX IF NOT EXISTS idx_cashflow_forecasting_projection_hub ON cashflow_forecasting_projection (hub_id, is_deleted);

-- Punto de proyección: un periodo con entradas/salidas y saldos de apertura/cierre.
-- source: recurring|expected|historical. Los importes los calcula el handler WASM.
CREATE TABLE IF NOT EXISTS cashflow_forecasting_point (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    projection_id   TEXT NOT NULL,
    period_start    TEXT NOT NULL,                    -- ISO YYYY-MM-DD
    period_end      TEXT NOT NULL,                    -- ISO YYYY-MM-DD
    opening_balance NUMERIC NOT NULL DEFAULT 0,
    total_inflows   NUMERIC NOT NULL DEFAULT 0,
    total_outflows  NUMERIC NOT NULL DEFAULT 0,
    closing_balance NUMERIC NOT NULL DEFAULT 0,
    net_change      NUMERIC NOT NULL DEFAULT 0,
    source          TEXT NOT NULL DEFAULT 'expected', -- recurring|expected|historical
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    FOREIGN KEY (projection_id) REFERENCES cashflow_forecasting_projection (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_cf_point_hub_projection ON cashflow_forecasting_point (hub_id, projection_id);
CREATE INDEX IF NOT EXISTS idx_cashflow_forecasting_point_hub ON cashflow_forecasting_point (hub_id, is_deleted);
