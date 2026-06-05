-- Stripe · esquema inicial (SQLite). Portado fielmente de old_modules/m_stripe/models.py.
-- Modelos: StripeConnection (cuenta Stripe conectada), StripeCharge (cargo observado vía
-- API/webhook), StripeRefund (devolución contra un cargo) y StripeWebhookEvent (envelope
-- de webhook, guardado para idempotencia + auditoría).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Cuenta Stripe configurada con la que habla el hub.
-- account_id (acct_xxx) es único por hub. Solo guardamos un hash del webhook secret.
CREATE TABLE IF NOT EXISTS stripe_connection (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    name                TEXT NOT NULL,
    account_id          TEXT NOT NULL,
    publishable_key     TEXT NOT NULL DEFAULT '',
    webhook_secret_hash TEXT NOT NULL DEFAULT '',
    is_active           INTEGER NOT NULL DEFAULT 1,
    is_test_mode        INTEGER NOT NULL DEFAULT 1,
    capabilities        TEXT NOT NULL DEFAULT '[]',  -- JSON: ["card_payments","transfers"]
    country             TEXT NOT NULL DEFAULT 'ES',
    default_currency    TEXT NOT NULL DEFAULT 'EUR',
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_stripe_conn_hub_acct  ON stripe_connection (hub_id, account_id);
CREATE INDEX        IF NOT EXISTS ix_stripe_conn_hub_active ON stripe_connection (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS idx_stripe_connection_hub ON stripe_connection (hub_id, is_deleted);

-- Cargo observado en una cuenta Stripe (vía API o webhook).
-- charge_id (ch_xxx) es único por hub → upsert idempotente en record_charge.
CREATE TABLE IF NOT EXISTS stripe_charge (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    connection_id     TEXT NOT NULL,
    charge_id         TEXT NOT NULL,                  -- Stripe charge id (ch_xxx)
    payment_intent_id TEXT NOT NULL DEFAULT '',       -- Stripe PaymentIntent id (pi_xxx)
    amount            NUMERIC NOT NULL DEFAULT 0,
    currency          TEXT NOT NULL DEFAULT 'EUR',
    status            TEXT NOT NULL DEFAULT 'pending', -- pending|succeeded|failed|canceled
    customer_email    TEXT NOT NULL DEFAULT '',
    payment_method    TEXT NOT NULL DEFAULT '',
    description       TEXT NOT NULL DEFAULT '',
    created_at_stripe TEXT,                            -- ISO datetime o NULL
    raw_event         TEXT,                            -- JSON crudo del evento o NULL
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    FOREIGN KEY (connection_id) REFERENCES stripe_connection (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_stripe_charge_hub_chid   ON stripe_charge (hub_id, charge_id);
CREATE INDEX        IF NOT EXISTS ix_stripe_charge_hub_status ON stripe_charge (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_stripe_charge_hub_conn   ON stripe_charge (hub_id, connection_id);
CREATE INDEX        IF NOT EXISTS idx_stripe_charge_hub       ON stripe_charge (hub_id, is_deleted);

-- Devolución emitida contra un cargo. refund_id (re_xxx) es único por hub.
CREATE TABLE IF NOT EXISTS stripe_refund (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    charge_id         TEXT NOT NULL,                  -- FK interna → stripe_charge.id
    refund_id         TEXT NOT NULL,                  -- Stripe refund id (re_xxx)
    amount            NUMERIC NOT NULL DEFAULT 0,
    status            TEXT NOT NULL DEFAULT 'succeeded', -- pending|succeeded|failed
    reason            TEXT NOT NULL DEFAULT '',
    created_at_stripe TEXT,                            -- ISO datetime o NULL
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    FOREIGN KEY (charge_id) REFERENCES stripe_charge (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_stripe_refund_hub_reid   ON stripe_refund (hub_id, refund_id);
CREATE INDEX        IF NOT EXISTS ix_stripe_refund_hub_charge ON stripe_refund (hub_id, charge_id);
CREATE INDEX        IF NOT EXISTS idx_stripe_refund_hub       ON stripe_refund (hub_id, is_deleted);

-- Evento de webhook recibido de Stripe (idempotencia + auditoría).
-- event_id (evt_xxx) es único por hub → record_webhook_event es no-op si ya existe.
CREATE TABLE IF NOT EXISTS stripe_webhook_event (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    connection_id TEXT NOT NULL,
    event_id      TEXT NOT NULL,                       -- Stripe event id (evt_xxx)
    event_type    TEXT NOT NULL,
    occurred_at   TEXT,                                -- ISO datetime o NULL
    processed_at  TEXT,                                -- ISO datetime o NULL
    status        TEXT NOT NULL DEFAULT 'received',    -- received|processing|processed|failed
    payload       TEXT,                                -- JSON del evento o NULL
    error_message TEXT NOT NULL DEFAULT '',
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT,
    FOREIGN KEY (connection_id) REFERENCES stripe_connection (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_stripe_evt_hub_eid    ON stripe_webhook_event (hub_id, event_id);
CREATE INDEX        IF NOT EXISTS ix_stripe_evt_hub_status ON stripe_webhook_event (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_stripe_evt_hub_type   ON stripe_webhook_event (hub_id, event_type);
CREATE INDEX        IF NOT EXISTS idx_stripe_webhook_event_hub ON stripe_webhook_event (hub_id, is_deleted);
