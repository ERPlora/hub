-- AI Predictions · esquema inicial (SQLite). Portado fielmente de
-- old_modules/m_ai_predictions/models.py.
-- Modelos: PredictionModel (predictor registrado), Prediction (predicción contra una
-- entidad) y PredictionFeedback (señal de acierto/error para medir precisión).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.
-- Nota: model/inference corren FUERA del hub; este módulo es catálogo + audit trail.

-- Modelo predictivo registrado. code es único por hub. prediction_type ∈
-- churn|lead_score|upsell|sales_forecast|risk|anomaly. features es JSON (lista de nombres).
CREATE TABLE IF NOT EXISTS ai_predictions_model (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    code            TEXT NOT NULL,
    name            TEXT NOT NULL,
    prediction_type TEXT NOT NULL DEFAULT 'churn',
    entity_type     TEXT NOT NULL DEFAULT '',
    model_version   TEXT NOT NULL DEFAULT '1.0.0',
    features        TEXT NOT NULL DEFAULT '[]',   -- JSON: lista de nombres de feature
    is_active       INTEGER NOT NULL DEFAULT 1,
    accuracy_score  NUMERIC,                       -- [0,1] o NULL si no evaluado
    trained_at      TEXT,                          -- ISO-8601 o NULL
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_pred_model_hub_code   ON ai_predictions_model (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_ai_pred_model_hub_active ON ai_predictions_model (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS ix_ai_pred_model_hub_type   ON ai_predictions_model (hub_id, prediction_type);
CREATE INDEX        IF NOT EXISTS idx_ai_predictions_model_hub ON ai_predictions_model (hub_id, is_deleted);

-- Una predicción generada por un PredictionModel contra una entidad. entity_ref es una
-- referencia libre (UUID de cliente, id de lead, sku…) — las entidades viven en otros módulos.
CREATE TABLE IF NOT EXISTS ai_predictions_prediction (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    model_id         TEXT NOT NULL,
    entity_ref       TEXT NOT NULL,
    prediction_value NUMERIC NOT NULL DEFAULT 0,
    confidence       NUMERIC NOT NULL DEFAULT 0,    -- [0,1]
    predicted_at     TEXT,                          -- ISO-8601 o NULL
    features_used    TEXT NOT NULL DEFAULT '{}',    -- JSON objeto
    explanation      TEXT NOT NULL DEFAULT '',
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT,
    FOREIGN KEY (model_id) REFERENCES ai_predictions_model (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_ai_pred_pred_hub_model     ON ai_predictions_prediction (hub_id, model_id);
CREATE INDEX IF NOT EXISTS ix_ai_pred_pred_hub_entity    ON ai_predictions_prediction (hub_id, entity_ref);
CREATE INDEX IF NOT EXISTS ix_ai_pred_pred_hub_predicted ON ai_predictions_prediction (hub_id, predicted_at);
CREATE INDEX IF NOT EXISTS idx_ai_predictions_prediction_hub ON ai_predictions_prediction (hub_id, is_deleted);

-- Feedback / ground-truth para una predicción. feedback_type ∈ correct|incorrect|partial.
-- Lo usa el cálculo de precisión (get_model_accuracy) — ver WASM-TODO.
CREATE TABLE IF NOT EXISTS ai_predictions_feedback (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    prediction_id TEXT NOT NULL,
    actual_value  NUMERIC,                          -- valor real observado o NULL
    feedback_type TEXT NOT NULL DEFAULT 'correct',
    notes         TEXT NOT NULL DEFAULT '',
    recorded_at   TEXT,                             -- ISO-8601 o NULL
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT,
    FOREIGN KEY (prediction_id) REFERENCES ai_predictions_prediction (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_ai_pred_feedback_hub_pred     ON ai_predictions_feedback (hub_id, prediction_id);
CREATE INDEX IF NOT EXISTS ix_ai_pred_feedback_hub_recorded ON ai_predictions_feedback (hub_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_ai_predictions_feedback_hub  ON ai_predictions_feedback (hub_id, is_deleted);
