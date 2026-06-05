-- Project Billing · esquema inicial (SQLite). Portado fielmente de old_modules/m_project_billing/models.py.
-- Modelos: BillingContract (contrato de facturación por proyecto: fixed_price / time_and_material /
-- milestone / retainer), BillingMilestone (hitos facturables del contrato), TimeEntry (partes de
-- horas imputadas al contrato) y ProjectInvoice (factura generada contra el contrato, con snapshot
-- JSON de hitos + horas en line_items).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Contrato de facturación por proyecto. contract_number se autogenera (PBC-YYYYMMDD-NNNN) en el
-- handler WASM (secuencia atómica por hub+día). billing_type ∈ fixed_price|time_and_material|
-- milestone|retainer. status ∈ draft|active|completed|cancelled.
-- project_ref / customer_name son enlaces sueltos (sin FK a otros módulos) — convención legacy.
CREATE TABLE IF NOT EXISTS project_billing_contract (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    contract_number TEXT NOT NULL,
    project_ref     TEXT NOT NULL DEFAULT '',
    customer_name   TEXT NOT NULL,
    billing_type    TEXT NOT NULL DEFAULT 'fixed_price',  -- fixed_price|time_and_material|milestone|retainer
    total_amount    NUMERIC NOT NULL DEFAULT 0,
    hourly_rate     NUMERIC NOT NULL DEFAULT 0,
    currency        TEXT NOT NULL DEFAULT 'EUR',
    start_date      TEXT,                                 -- ISO YYYY-MM-DD o NULL
    end_date        TEXT,                                 -- ISO YYYY-MM-DD o NULL
    status          TEXT NOT NULL DEFAULT 'draft',        -- draft|active|completed|cancelled
    notes           TEXT NOT NULL DEFAULT '',
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_project_billing_contract_hub     ON project_billing_contract (hub_id, is_deleted);
CREATE INDEX IF NOT EXISTS ix_pb_contract_hub_status            ON project_billing_contract (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_pb_contract_hub_project           ON project_billing_contract (hub_id, project_ref);
CREATE INDEX IF NOT EXISTS ix_pb_contract_hub_number            ON project_billing_contract (hub_id, contract_number);
CREATE INDEX IF NOT EXISTS ix_pb_contract_hub_type              ON project_billing_contract (hub_id, billing_type);

-- Hito facturable asociado a un contrato. status ∈ pending|invoiced|paid.
-- invoiced_at / paid_at son sellos de tiempo de transición de estado.
CREATE TABLE IF NOT EXISTS project_billing_milestone (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    contract_id  TEXT NOT NULL,
    name         TEXT NOT NULL,
    due_date     TEXT,                                    -- ISO YYYY-MM-DD o NULL
    amount       NUMERIC NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'pending',         -- pending|invoiced|paid
    invoiced_at  TEXT,                                    -- ISO 8601 o NULL
    paid_at      TEXT,                                    -- ISO 8601 o NULL
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT,
    FOREIGN KEY (contract_id) REFERENCES project_billing_contract (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_project_billing_milestone_hub ON project_billing_milestone (hub_id, is_deleted);
CREATE INDEX IF NOT EXISTS ix_pb_milestone_contract          ON project_billing_milestone (contract_id);
CREATE INDEX IF NOT EXISTS ix_pb_milestone_hub_status        ON project_billing_milestone (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_pb_milestone_hub_due           ON project_billing_milestone (hub_id, due_date);

-- Parte de horas imputado a un contrato. line_total = hours * hourly_rate (lo calcula el WASM/UI;
-- aquí se almacenan los inputs). is_invoiced marca que ya entró en una factura.
CREATE TABLE IF NOT EXISTS project_billing_time_entry (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    contract_id  TEXT NOT NULL,
    entry_date   TEXT,                                    -- ISO YYYY-MM-DD o NULL
    hours        NUMERIC NOT NULL DEFAULT 0,
    hourly_rate  NUMERIC NOT NULL DEFAULT 0,
    employee_ref TEXT NOT NULL DEFAULT '',
    description  TEXT NOT NULL DEFAULT '',
    is_invoiced  INTEGER NOT NULL DEFAULT 0,
    invoiced_at  TEXT,                                    -- ISO 8601 o NULL
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT,
    FOREIGN KEY (contract_id) REFERENCES project_billing_contract (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_project_billing_time_entry_hub ON project_billing_time_entry (hub_id, is_deleted);
CREATE INDEX IF NOT EXISTS ix_pb_time_contract               ON project_billing_time_entry (contract_id);
CREATE INDEX IF NOT EXISTS ix_pb_time_hub_date               ON project_billing_time_entry (hub_id, entry_date);
CREATE INDEX IF NOT EXISTS ix_pb_time_hub_employee           ON project_billing_time_entry (hub_id, employee_ref);
CREATE INDEX IF NOT EXISTS ix_pb_time_hub_invoiced           ON project_billing_time_entry (hub_id, is_invoiced);

-- Factura de proyecto generada contra un contrato. invoice_number se autogenera (PIV-YYYYMMDD-NNNN)
-- en el handler WASM. status ∈ draft|sent|paid|cancelled. line_items es un snapshot JSON de los
-- hitos + partes de horas incluidos en la factura en el momento de generarla.
CREATE TABLE IF NOT EXISTS project_billing_invoice (
    id             TEXT PRIMARY KEY,
    hub_id         TEXT NOT NULL,
    contract_id    TEXT NOT NULL,
    invoice_number TEXT NOT NULL,
    invoice_date   TEXT,                                  -- ISO YYYY-MM-DD o NULL
    due_date       TEXT,                                  -- ISO YYYY-MM-DD o NULL
    amount         NUMERIC NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'draft',         -- draft|sent|paid|cancelled
    line_items     TEXT,                                  -- JSON: [{type, id, ...}]
    is_deleted     INTEGER NOT NULL DEFAULT 0,
    deleted_at     TEXT,
    created_by     TEXT,
    updated_by     TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT,
    FOREIGN KEY (contract_id) REFERENCES project_billing_contract (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_project_billing_invoice_hub ON project_billing_invoice (hub_id, is_deleted);
CREATE INDEX IF NOT EXISTS ix_pb_invoice_contract          ON project_billing_invoice (contract_id);
CREATE INDEX IF NOT EXISTS ix_pb_invoice_hub_status        ON project_billing_invoice (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_pb_invoice_hub_number        ON project_billing_invoice (hub_id, invoice_number);
CREATE INDEX IF NOT EXISTS ix_pb_invoice_hub_date          ON project_billing_invoice (hub_id, invoice_date);
