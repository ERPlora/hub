-- Subscriptions · esquema inicial (SQLite). Portado fielmente de old_modules/m_subscriptions/models.py.
-- Modelos: Plan (catálogo: precio + periodo de facturación), Subscription (cliente ↔ plan + ciclo
-- de vida trialing→active→cancelled/expired) y BillingCycle (un periodo facturado dentro de una
-- suscripción: pending→invoiced→paid/failed).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Plan de suscripción: entrada de catálogo con precio por periodo de facturación.
-- code es único por hub y es el identificador estable de cara a otros módulos/UI.
-- billing_period ∈ (monthly|quarterly|yearly); features es JSON libre opcional.
CREATE TABLE IF NOT EXISTS subscriptions_plan (
    id             TEXT PRIMARY KEY,
    hub_id         TEXT NOT NULL,
    code           TEXT NOT NULL,
    name           TEXT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    billing_period TEXT NOT NULL DEFAULT 'monthly',   -- monthly|quarterly|yearly
    price          NUMERIC NOT NULL DEFAULT 0,
    trial_days     INTEGER NOT NULL DEFAULT 0,
    features       TEXT,                               -- JSON libre (flags/límites) o NULL
    is_active      INTEGER NOT NULL DEFAULT 1,
    is_deleted     INTEGER NOT NULL DEFAULT 0,
    deleted_at     TEXT,
    created_by     TEXT,
    updated_by     TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_subscriptions_plan_hub_code ON subscriptions_plan (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_subscriptions_plan_hub_active ON subscriptions_plan (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS idx_subscriptions_plan_hub ON subscriptions_plan (hub_id, is_deleted);

-- Suscripción: vincula un cliente (datos sueltos, sin FK a Customer) a un Plan y
-- registra el ciclo de vida y las fechas del periodo vigente.
-- status ∈ (trialing|active|past_due|cancelled|expired).
CREATE TABLE IF NOT EXISTS subscriptions_subscription (
    id                   TEXT PRIMARY KEY,
    hub_id               TEXT NOT NULL,
    plan_id              TEXT NOT NULL,
    customer_name        TEXT NOT NULL,
    customer_email       TEXT NOT NULL DEFAULT '',
    customer_tax_id      TEXT NOT NULL DEFAULT '',
    status               TEXT NOT NULL DEFAULT 'trialing',
    start_date           TEXT NOT NULL,                 -- ISO YYYY-MM-DD
    current_period_start TEXT,                           -- ISO YYYY-MM-DD o NULL
    current_period_end   TEXT,                           -- ISO YYYY-MM-DD o NULL
    trial_end            TEXT,                           -- ISO YYYY-MM-DD o NULL
    cancelled_at         TEXT,                           -- ISO YYYY-MM-DD o NULL
    cancellation_reason  TEXT NOT NULL DEFAULT '',
    is_deleted           INTEGER NOT NULL DEFAULT 0,
    deleted_at           TEXT,
    created_by           TEXT,
    updated_by           TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT,
    FOREIGN KEY (plan_id) REFERENCES subscriptions_plan (id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS ix_subscriptions_sub_hub_status   ON subscriptions_subscription (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_subscriptions_sub_hub_customer ON subscriptions_subscription (hub_id, customer_name);
CREATE INDEX IF NOT EXISTS ix_subscriptions_sub_hub_plan     ON subscriptions_subscription (hub_id, plan_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_subscription_hub ON subscriptions_subscription (hub_id, is_deleted);

-- Ciclo de facturación: un periodo cobrado dentro de una suscripción.
-- status ∈ (pending|invoiced|paid|failed); amount se congela del precio del plan en la generación.
CREATE TABLE IF NOT EXISTS subscriptions_billing_cycle (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    subscription_id TEXT NOT NULL,
    period_start    TEXT NOT NULL,                       -- ISO YYYY-MM-DD
    period_end      TEXT NOT NULL,                       -- ISO YYYY-MM-DD
    amount          NUMERIC NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'pending',
    invoiced_at     TEXT,                                -- ISO YYYY-MM-DD o NULL
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    FOREIGN KEY (subscription_id) REFERENCES subscriptions_subscription (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_subscriptions_cycle_hub_sub    ON subscriptions_billing_cycle (hub_id, subscription_id);
CREATE INDEX IF NOT EXISTS ix_subscriptions_cycle_hub_status ON subscriptions_billing_cycle (hub_id, status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_billing_cycle_hub ON subscriptions_billing_cycle (hub_id, is_deleted);
