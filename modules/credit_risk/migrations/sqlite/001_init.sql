-- Credit Risk · esquema inicial (SQLite). Portado fielmente de old_modules/m_credit_risk/models.py.
-- Modelos: CustomerCredit (perfil de crédito por cliente: límite, exposición, score, estado),
-- CreditEvent (bitácora de eventos que mutan la exposición: facturas, pagos, revisiones) y
-- CreditAlert (alertas levantadas al cruzar umbrales).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Perfil de crédito por cliente. customer_ref identifica al cliente (sin FK: el módulo
-- customers puede no estar instalado). customer_ref es único por hub.
CREATE TABLE IF NOT EXISTS credit_risk_customer (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    customer_ref        TEXT NOT NULL,
    customer_name       TEXT NOT NULL,
    credit_limit        NUMERIC NOT NULL DEFAULT 0,
    payment_terms_days  INTEGER NOT NULL DEFAULT 30,
    current_exposure    NUMERIC NOT NULL DEFAULT 0,
    credit_score        INTEGER NOT NULL DEFAULT 0,
    score_calculated_at TEXT,
    status              TEXT NOT NULL DEFAULT 'active',  -- active|on_hold|blocked
    notes               TEXT NOT NULL DEFAULT '',
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_credit_hub_customer_ref  ON credit_risk_customer (hub_id, customer_ref);
CREATE INDEX        IF NOT EXISTS ix_credit_hub_status        ON credit_risk_customer (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_credit_hub_score         ON credit_risk_customer (hub_id, credit_score);
CREATE INDEX        IF NOT EXISTS idx_credit_risk_customer_hub ON credit_risk_customer (hub_id, is_deleted);

-- Evento de crédito: una entrada en la bitácora de un cliente (factura/pago/revisión...).
-- amount es el importe del evento; occurred_at cuándo ocurrió. La mutación de la exposición
-- y el disparo de alertas los hace el runtime/WASM, no esta tabla (ver WASM-TODO).
CREATE TABLE IF NOT EXISTS credit_risk_event (
    id                 TEXT PRIMARY KEY,
    hub_id             TEXT NOT NULL,
    customer_credit_id TEXT NOT NULL,
    event_type         TEXT NOT NULL,  -- invoice_issued|payment_received|limit_exceeded|late_payment|score_updated|manual_review
    amount             NUMERIC NOT NULL DEFAULT 0,
    description        TEXT NOT NULL DEFAULT '',
    occurred_at        TEXT NOT NULL,
    reference          TEXT NOT NULL DEFAULT '',
    is_deleted         INTEGER NOT NULL DEFAULT 0,
    deleted_at         TEXT,
    created_by         TEXT,
    updated_by         TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT,
    FOREIGN KEY (customer_credit_id) REFERENCES credit_risk_customer (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_credit_event_hub_customer ON credit_risk_event (hub_id, customer_credit_id);
CREATE INDEX IF NOT EXISTS ix_credit_event_hub_type     ON credit_risk_event (hub_id, event_type);
CREATE INDEX IF NOT EXISTS ix_credit_event_hub_occurred ON credit_risk_event (hub_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_credit_risk_event_hub    ON credit_risk_event (hub_id, is_deleted);

-- Alerta de crédito: levantada cuando un cliente cruza un umbral (límite, atraso, score).
-- acknowledged_at/resolved_at marcan su ciclo de vida; acknowledged_by_ref el actor.
CREATE TABLE IF NOT EXISTS credit_risk_alert (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    customer_credit_id  TEXT NOT NULL,
    alert_type          TEXT NOT NULL,  -- limit_warning_80pct|limit_exceeded|payment_overdue|score_dropped
    severity            TEXT NOT NULL DEFAULT 'info',  -- info|warning|critical
    triggered_at        TEXT NOT NULL,
    acknowledged_at     TEXT,
    acknowledged_by_ref TEXT NOT NULL DEFAULT '',
    resolved_at         TEXT,
    notes               TEXT NOT NULL DEFAULT '',
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT,
    FOREIGN KEY (customer_credit_id) REFERENCES credit_risk_customer (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_credit_alert_hub_customer  ON credit_risk_alert (hub_id, customer_credit_id);
CREATE INDEX IF NOT EXISTS ix_credit_alert_hub_type      ON credit_risk_alert (hub_id, alert_type);
CREATE INDEX IF NOT EXISTS ix_credit_alert_hub_severity  ON credit_risk_alert (hub_id, severity);
CREATE INDEX IF NOT EXISTS ix_credit_alert_hub_triggered ON credit_risk_alert (hub_id, triggered_at);
CREATE INDEX IF NOT EXISTS idx_credit_risk_alert_hub     ON credit_risk_alert (hub_id, is_deleted);
