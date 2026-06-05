-- Contracts · esquema inicial (SQLite). Portado fielmente de old_modules/m_contracts/models.py.
-- Modelos: Contract (acuerdo de cliente con ciclo de vida draft→active→suspended/terminated/expired,
-- importe mensual/total, auto-renovación y nº auto COR-YYYYMMDD-NNNN) y ContractMilestone
-- (hito de facturación asociado a un contrato).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Contrato de cliente: servicio recurrente, mantenimiento o acuerdo puntual.
-- contract_number es el identificador legible auto-generado por hub+día (COR-YYYYMMDD-NNNN).
-- customer_* es un vínculo laxo (sin FK a un modelo Customer): el módulo OWNea sus filas.
CREATE TABLE IF NOT EXISTS contracts_contract (
    id                    TEXT PRIMARY KEY,
    hub_id                TEXT NOT NULL,
    contract_number       TEXT NOT NULL,
    customer_name         TEXT NOT NULL,
    customer_email        TEXT NOT NULL DEFAULT '',
    customer_tax_id       TEXT NOT NULL DEFAULT '',
    contract_type         TEXT NOT NULL DEFAULT 'service',   -- service|recurring|maintenance|other
    status                TEXT NOT NULL DEFAULT 'draft',     -- draft|active|suspended|terminated|expired
    start_date            TEXT,                              -- ISO YYYY-MM-DD o NULL
    end_date              TEXT,                              -- ISO YYYY-MM-DD o NULL
    monthly_amount        NUMERIC NOT NULL DEFAULT 0,
    total_amount          NUMERIC NOT NULL DEFAULT 0,
    auto_renew            INTEGER NOT NULL DEFAULT 0,
    renewal_period_months INTEGER NOT NULL DEFAULT 0,
    notes                 TEXT NOT NULL DEFAULT '',
    terms                 TEXT NOT NULL DEFAULT '',
    is_deleted            INTEGER NOT NULL DEFAULT 0,
    deleted_at            TEXT,
    created_by            TEXT,
    updated_by            TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT
);
CREATE INDEX IF NOT EXISTS idx_contracts_contract_hub      ON contracts_contract (hub_id, is_deleted);
CREATE INDEX IF NOT EXISTS ix_contracts_hub_status         ON contracts_contract (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_contracts_hub_customer       ON contracts_contract (hub_id, customer_name);
CREATE INDEX IF NOT EXISTS ix_contracts_hub_number         ON contracts_contract (hub_id, contract_number);
CREATE INDEX IF NOT EXISTS ix_contracts_hub_end_date       ON contracts_contract (hub_id, end_date);

-- Hito de facturación de un contrato. contract_id referencia al contrato propietario.
-- is_invoiced/invoiced_at registran el estado de facturación del hito.
CREATE TABLE IF NOT EXISTS contracts_milestone (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    contract_id  TEXT NOT NULL,
    description  TEXT NOT NULL,
    due_date     TEXT,                              -- ISO YYYY-MM-DD o NULL
    amount       NUMERIC NOT NULL DEFAULT 0,
    is_invoiced  INTEGER NOT NULL DEFAULT 0,
    invoiced_at  TEXT,                              -- ISO timestamp o NULL
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT,
    FOREIGN KEY (contract_id) REFERENCES contracts_contract (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_contracts_milestone_hub      ON contracts_milestone (hub_id, is_deleted);
CREATE INDEX IF NOT EXISTS ix_contracts_milestone_contract  ON contracts_milestone (contract_id);
CREATE INDEX IF NOT EXISTS ix_contracts_milestone_due       ON contracts_milestone (hub_id, due_date);
