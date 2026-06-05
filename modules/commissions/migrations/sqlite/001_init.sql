-- Commissions · esquema inicial (SQLite). Portado de old_modules/m_commissions/models.py.
-- Modelos: CommissionsSettings (singleton por hub), CommissionRule, CommissionTransaction,
--          CommissionPayout, CommissionAdjustment.
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.
--
-- Cross-módulo: las antiguas FK a staff_member / services_service / services_category /
-- inventory_product / sales_sale / appointments_appointment se degradan a columnas TEXT
-- (snapshot de id). Este módulo NO toca tablas de otros módulos: cualquier resolución
-- (nombre de staff, etc.) llega por payload del comando o vía queries públicas de esos
-- módulos. Cada módulo OWNea sus propias tablas.

-- Ajustes de comisiones del hub (singleton: único por hub_id).
-- calculation_basis: gross|net|profit. payout_frequency: weekly|biweekly|monthly|custom.
CREATE TABLE IF NOT EXISTS commissions_settings (
    id                          TEXT PRIMARY KEY,
    hub_id                      TEXT NOT NULL,
    default_commission_rate     NUMERIC NOT NULL DEFAULT 10.00,
    calculation_basis           TEXT NOT NULL DEFAULT 'net',
    payout_frequency            TEXT NOT NULL DEFAULT 'monthly',
    payout_day                  INTEGER NOT NULL DEFAULT 1,
    minimum_payout_amount       NUMERIC NOT NULL DEFAULT 0.00,
    apply_tax_withholding       INTEGER NOT NULL DEFAULT 0,
    tax_withholding_rate        NUMERIC NOT NULL DEFAULT 0.00,
    show_commission_on_receipt  INTEGER NOT NULL DEFAULT 0,
    show_pending_commission     INTEGER NOT NULL DEFAULT 1,
    is_deleted                  INTEGER NOT NULL DEFAULT 0,
    deleted_at                  TEXT,
    created_by                  TEXT,
    updated_by                  TEXT,
    created_at                  TEXT NOT NULL,
    updated_at                  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_commissions_settings_hub ON commissions_settings (hub_id);
CREATE INDEX        IF NOT EXISTS idx_commissions_settings_hub ON commissions_settings (hub_id, is_deleted);

-- Regla de comisión: flat|percentage|tiered. rate es % (percentage) o importe fijo (flat).
-- tier_thresholds es JSON [{min_amount,max_amount,rate}] usado solo por rule_type='tiered'.
-- Las columnas *_id son referencias opcionales (snapshot) a entidades de otros módulos.
CREATE TABLE IF NOT EXISTS commissions_rule (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    rule_type       TEXT NOT NULL DEFAULT 'percentage',   -- flat|percentage|tiered
    rate            NUMERIC NOT NULL DEFAULT 0.00,
    staff_id        TEXT,                                  -- ref. staff (otro módulo); NULL = global
    service_id      TEXT,                                  -- ref. services (otro módulo)
    category_id     TEXT,                                  -- ref. services category (otro módulo)
    product_id      TEXT,                                  -- ref. inventory (otro módulo)
    tier_thresholds TEXT NOT NULL DEFAULT '[]',            -- JSON [{min_amount,max_amount,rate}]
    effective_from  TEXT,                                  -- ISO YYYY-MM-DD o NULL
    effective_until TEXT,                                  -- ISO YYYY-MM-DD o NULL
    priority        INTEGER NOT NULL DEFAULT 0,
    is_active       INTEGER NOT NULL DEFAULT 1,
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);
CREATE INDEX IF NOT EXISTS ix_commissions_rule_hub_priority ON commissions_rule (hub_id, priority);
CREATE INDEX IF NOT EXISTS idx_commissions_rule_hub         ON commissions_rule (hub_id, is_deleted);

-- Transacción de comisión: un devengo individual para un staff (snapshot staff_name).
-- status: pending|approved|paid|cancelled|adjusted. payout_id liga al lote de pago.
CREATE TABLE IF NOT EXISTS commissions_transaction (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    staff_id         TEXT,                                 -- ref. staff (otro módulo)
    staff_name       TEXT NOT NULL,
    sale_id          TEXT,                                 -- ref. sales (otro módulo)
    sale_reference   TEXT NOT NULL DEFAULT '',
    appointment_id   TEXT,                                 -- ref. appointments (otro módulo)
    sale_amount      NUMERIC NOT NULL DEFAULT 0,
    commission_rate  NUMERIC NOT NULL DEFAULT 0,
    commission_amount NUMERIC NOT NULL DEFAULT 0,
    tax_amount       NUMERIC NOT NULL DEFAULT 0.00,
    net_commission   NUMERIC NOT NULL DEFAULT 0,
    rule_id          TEXT,                                 -- ref. commissions_rule (propia)
    status           TEXT NOT NULL DEFAULT 'pending',      -- pending|approved|paid|cancelled|adjusted
    payout_id        TEXT,                                 -- ref. commissions_payout (propia)
    transaction_date TEXT NOT NULL,                        -- ISO YYYY-MM-DD
    approved_at      TEXT,
    approved_by_id   TEXT,
    description      TEXT NOT NULL DEFAULT '',
    notes            TEXT NOT NULL DEFAULT '',
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT
);
CREATE INDEX IF NOT EXISTS ix_commissions_trans_hub_staff_status ON commissions_transaction (hub_id, staff_id, status);
CREATE INDEX IF NOT EXISTS ix_commissions_trans_hub_date         ON commissions_transaction (hub_id, transaction_date);
CREATE INDEX IF NOT EXISTS ix_commissions_trans_hub_payout       ON commissions_transaction (hub_id, payout_id);
CREATE INDEX IF NOT EXISTS idx_commissions_transaction_hub       ON commissions_transaction (hub_id, is_deleted);

-- Lote de pago de comisiones por staff y periodo. Agrega N transacciones aprobadas.
-- status: draft|pending|approved|processing|completed|failed|cancelled|included_in_payslip.
CREATE TABLE IF NOT EXISTS commissions_payout (
    id                 TEXT PRIMARY KEY,
    hub_id             TEXT NOT NULL,
    reference          TEXT NOT NULL,
    staff_id           TEXT,                               -- ref. staff (otro módulo)
    staff_name         TEXT NOT NULL,
    period_start       TEXT NOT NULL,                      -- ISO YYYY-MM-DD
    period_end         TEXT NOT NULL,                      -- ISO YYYY-MM-DD
    gross_amount       NUMERIC NOT NULL DEFAULT 0.00,
    tax_amount         NUMERIC NOT NULL DEFAULT 0.00,
    adjustments_amount NUMERIC NOT NULL DEFAULT 0.00,
    net_amount         NUMERIC NOT NULL DEFAULT 0.00,
    transaction_count  INTEGER NOT NULL DEFAULT 0,
    status             TEXT NOT NULL DEFAULT 'draft',
    payment_method     TEXT NOT NULL DEFAULT '',           -- cash|bank_transfer|check|payroll|other
    payment_reference  TEXT NOT NULL DEFAULT '',
    approved_at        TEXT,
    approved_by_id     TEXT,
    paid_at            TEXT,
    paid_by_id         TEXT,
    notes              TEXT NOT NULL DEFAULT '',
    payslip_id         TEXT,                               -- ref. payroll (otro módulo) cuando se incluye en nómina
    is_deleted         INTEGER NOT NULL DEFAULT 0,
    deleted_at         TEXT,
    created_by         TEXT,
    updated_by         TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT
);
CREATE INDEX IF NOT EXISTS ix_commissions_payout_hub_status ON commissions_payout (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_commissions_payout_hub_staff  ON commissions_payout (hub_id, staff_id);
CREATE INDEX IF NOT EXISTS idx_commissions_payout_hub       ON commissions_payout (hub_id, is_deleted);

-- Ajuste manual sobre comisiones: bonus|correction|deduction|refund_adjustment|other.
-- amount puede ser negativo (deducción). payout_id liga el ajuste a un lote (opcional).
CREATE TABLE IF NOT EXISTS commissions_adjustment (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    staff_id         TEXT,                                 -- ref. staff (otro módulo)
    staff_name       TEXT NOT NULL,
    adjustment_type  TEXT NOT NULL DEFAULT 'correction',   -- bonus|correction|deduction|refund_adjustment|other
    amount           NUMERIC NOT NULL DEFAULT 0,
    reason           TEXT NOT NULL,
    payout_id        TEXT,                                 -- ref. commissions_payout (propia)
    adjustment_date  TEXT NOT NULL,                        -- ISO YYYY-MM-DD
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT
);
CREATE INDEX IF NOT EXISTS ix_commissions_adj_hub_staff  ON commissions_adjustment (hub_id, staff_id);
CREATE INDEX IF NOT EXISTS ix_commissions_adj_hub_payout ON commissions_adjustment (hub_id, payout_id);
CREATE INDEX IF NOT EXISTS idx_commissions_adjustment_hub ON commissions_adjustment (hub_id, is_deleted);
