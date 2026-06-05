-- Forecasting · esquema inicial (SQLite). Portado fielmente de old_modules/m_forecasting/models.py.
-- Modelos: ForecastModel (predictor configurable: tipo + métrica objetivo + parámetros),
-- Forecast (una ejecución de pronóstico: horizonte + estado + precisión) y
-- ForecastPoint (valor predicho por periodo con bandas de confianza).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Predictor configurado: tipo de modelo + métrica objetivo + parámetros JSON.
-- code es único por hub. model_type ∈ moving_average|linear_trend|exponential_smoothing|seasonal|manual.
-- target_metric ∈ sales|demand|cashflow|inventory.
CREATE TABLE IF NOT EXISTS forecasting_model (
    id                    TEXT PRIMARY KEY,
    hub_id                TEXT NOT NULL,
    code                  TEXT NOT NULL,
    name                  TEXT NOT NULL,
    model_type            TEXT NOT NULL DEFAULT 'moving_average',
    target_metric         TEXT NOT NULL DEFAULT 'sales',
    parameters            TEXT NOT NULL DEFAULT '{}',   -- JSON con parámetros del modelo (p.ej. {"window":3})
    training_period_days  INTEGER NOT NULL DEFAULT 90,
    is_active             INTEGER NOT NULL DEFAULT 1,
    last_trained_at       TEXT,                          -- ISO datetime o NULL
    is_deleted            INTEGER NOT NULL DEFAULT 0,
    deleted_at            TEXT,
    created_by            TEXT,
    updated_by            TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_forecasting_model_hub_code   ON forecasting_model (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_forecasting_model_hub_active ON forecasting_model (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS ix_forecasting_model_hub_target ON forecasting_model (hub_id, target_metric);
CREATE INDEX        IF NOT EXISTS idx_forecasting_model_hub       ON forecasting_model (hub_id, is_deleted);

-- Una ejecución de pronóstico para un modelo concreto.
-- status ∈ running|completed|failed. period_unit ∈ day|week|month|quarter.
-- accuracy_score (0..1) se rellena tras comparar contra valores reales (record_accuracy).
CREATE TABLE IF NOT EXISTS forecasting_forecast (
    id                       TEXT PRIMARY KEY,
    hub_id                   TEXT NOT NULL,
    model_id                 TEXT NOT NULL,
    forecast_number          TEXT NOT NULL,
    forecast_horizon_periods INTEGER NOT NULL DEFAULT 12,
    period_unit              TEXT NOT NULL DEFAULT 'month',
    generated_at             TEXT,                       -- ISO datetime o NULL
    generated_by_ref         TEXT NOT NULL DEFAULT '',
    status                   TEXT NOT NULL DEFAULT 'running',
    accuracy_score           NUMERIC,                    -- 0..1 (1 - MAPE) o NULL
    notes                    TEXT NOT NULL DEFAULT '',
    is_deleted               INTEGER NOT NULL DEFAULT 0,
    deleted_at               TEXT,
    created_by               TEXT,
    updated_by               TEXT,
    created_at               TEXT NOT NULL,
    updated_at               TEXT,
    FOREIGN KEY (model_id) REFERENCES forecasting_model (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_forecasting_forecast_hub_status    ON forecasting_forecast (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_forecasting_forecast_hub_model     ON forecasting_forecast (hub_id, model_id);
CREATE INDEX IF NOT EXISTS ix_forecasting_forecast_hub_generated ON forecasting_forecast (hub_id, generated_at);
CREATE INDEX IF NOT EXISTS idx_forecasting_forecast_hub          ON forecasting_forecast (hub_id, is_deleted);

-- Valor predicho para un periodo concreto, con bandas de confianza (lower/upper) y nivel.
CREATE TABLE IF NOT EXISTS forecasting_point (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    forecast_id     TEXT NOT NULL,
    period_start    TEXT NOT NULL,                       -- ISO YYYY-MM-DD
    period_end      TEXT NOT NULL,                       -- ISO YYYY-MM-DD
    predicted_value NUMERIC NOT NULL DEFAULT 0,
    lower_bound     NUMERIC,
    upper_bound     NUMERIC,
    confidence      NUMERIC NOT NULL DEFAULT 0.9500,
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    FOREIGN KEY (forecast_id) REFERENCES forecasting_forecast (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_forecasting_point_hub_forecast ON forecasting_point (hub_id, forecast_id);
CREATE INDEX IF NOT EXISTS idx_forecasting_point_hub         ON forecasting_point (hub_id, is_deleted);
