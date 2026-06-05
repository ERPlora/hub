-- Payment Gateways · esquema inicial (SQLite). Portado fielmente de modules/m_payment_gateways/models.py.
-- Modelos: PaymentGateway, PaymentTransaction, PaymentRefund + PaymentTransactionCounter (interno).
-- Registro provider-agnóstico de pasarelas (Stripe/Redsys/PayPal/manual/other) + libro unificado
-- de transacciones y reembolsos. Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Pasarela de pago configurada en el hub.
CREATE TABLE IF NOT EXISTS payment_gateways_gateway (
    id                   TEXT PRIMARY KEY,
    hub_id               TEXT NOT NULL,
    code                 TEXT NOT NULL,                       -- identificador estable único por hub (p.ej. stripe_main)
    name                 TEXT NOT NULL,
    provider             TEXT NOT NULL DEFAULT 'manual',      -- stripe|redsys|paypal|manual|other
    is_active            INTEGER NOT NULL DEFAULT 1,
    is_test_mode         INTEGER NOT NULL DEFAULT 1,
    config               TEXT NOT NULL DEFAULT '{}',          -- JSON con claves del proveedor (secretos enmascarados al exponer)
    supports_refunds     INTEGER NOT NULL DEFAULT 1,
    supported_currencies TEXT NOT NULL DEFAULT '[]',          -- JSON array de códigos ISO-4217
    is_deleted           INTEGER NOT NULL DEFAULT 0,
    deleted_at           TEXT,
    created_by           TEXT,
    updated_by           TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_gateway_hub_code ON payment_gateways_gateway (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_pg_hub_provider          ON payment_gateways_gateway (hub_id, provider);
CREATE INDEX        IF NOT EXISTS ix_pg_hub_active            ON payment_gateways_gateway (hub_id, is_active);

-- Transacción contra una pasalera (libro unificado entre proveedores).
CREATE TABLE IF NOT EXISTS payment_gateways_transaction (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    gateway_id          TEXT NOT NULL,
    transaction_id      TEXT NOT NULL DEFAULT '',             -- id del proveedor (pi_… en Stripe); vacío mientras está pending
    reference           TEXT NOT NULL,                        -- único por hub: PT-YYYYMMDD-NNNN
    amount              NUMERIC NOT NULL,
    currency            TEXT NOT NULL DEFAULT 'EUR',
    status              TEXT NOT NULL DEFAULT 'pending',      -- pending|processing|succeeded|failed|refunded|partially_refunded
    customer_email      TEXT NOT NULL DEFAULT '',
    payment_method_type TEXT NOT NULL DEFAULT 'card',
    error_code          TEXT NOT NULL DEFAULT '',
    error_message       TEXT NOT NULL DEFAULT '',
    raw_response        TEXT,                                 -- JSON con la respuesta cruda del proveedor
    captured_at         TEXT,
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT,
    FOREIGN KEY (gateway_id) REFERENCES payment_gateways_gateway (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_tx_hub_reference ON payment_gateways_transaction (hub_id, reference);
CREATE INDEX        IF NOT EXISTS ix_pg_tx_hub_status         ON payment_gateways_transaction (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_pg_tx_hub_gateway        ON payment_gateways_transaction (hub_id, gateway_id);
CREATE INDEX        IF NOT EXISTS ix_pg_tx_hub_email          ON payment_gateways_transaction (hub_id, customer_email);

-- Reembolso (parcial o total) sobre una transacción succeeded.
CREATE TABLE IF NOT EXISTS payment_gateways_refund (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    transaction_id      TEXT NOT NULL,
    amount_refunded     NUMERIC NOT NULL,
    reason              TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'pending',      -- pending|succeeded|failed
    refund_provider_id  TEXT NOT NULL DEFAULT '',             -- id del reembolso del proveedor una vez emitido
    refunded_at         TEXT,
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT,
    FOREIGN KEY (transaction_id) REFERENCES payment_gateways_transaction (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_pg_refund_hub_tx     ON payment_gateways_refund (hub_id, transaction_id);
CREATE INDEX IF NOT EXISTS ix_pg_refund_hub_status ON payment_gateways_refund (hub_id, status);

-- Contador interno por hub y día. Respalda el generador atómico de referencias PT-YYYYMMDD-NNNN.
-- El upsert atómico (INSERT ... ON CONFLICT DO UPDATE ... RETURNING) vive en el handler WASM (ver WASM-TODO.md).
CREATE TABLE IF NOT EXISTS payment_gateways_counter (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    day         TEXT NOT NULL,                                -- YYYYMMDD
    last_number INTEGER NOT NULL DEFAULT 0,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_tx_counter_hub_day ON payment_gateways_counter (hub_id, day);