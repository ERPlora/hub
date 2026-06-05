-- Credit Notes · esquema inicial (SQLite). Portado fielmente de old_modules/m_credit_notes/models.py.
-- Modelos: CreditNote, CreditNoteLine, CreditNoteApplication, CreditNoteCounter.
-- Una nota de abono (abono) en dos direcciones: issued_to_customer | received_from_supplier.
-- Ciclo de vida: draft -> issued -> applied (parcial/total) | cancelled.
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Nota de abono (cabecera).
CREATE TABLE IF NOT EXISTS credit_notes_note (
    id                   TEXT PRIMARY KEY,
    hub_id               TEXT NOT NULL,
    credit_note_number   TEXT NOT NULL,                 -- CN-YYYYMMDD-NNNN (único por hub)
    direction            TEXT NOT NULL,                 -- issued_to_customer|received_from_supplier
    counterparty_name    TEXT NOT NULL,
    counterparty_tax_id  TEXT NOT NULL DEFAULT '',
    issue_date           TEXT,                          -- ISO date (YYYY-MM-DD) o NULL
    original_invoice_ref TEXT NOT NULL DEFAULT '',      -- ref suelta a la factura original (sin FK)
    total_amount         NUMERIC NOT NULL DEFAULT 0,
    tax_amount           NUMERIC NOT NULL DEFAULT 0,
    applied_amount       NUMERIC NOT NULL DEFAULT 0,
    reason               TEXT NOT NULL DEFAULT '',
    status               TEXT NOT NULL DEFAULT 'draft', -- draft|issued|applied|cancelled
    notes                TEXT NOT NULL DEFAULT '',
    is_deleted           INTEGER NOT NULL DEFAULT 0,
    deleted_at           TEXT,
    created_by           TEXT,
    updated_by           TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_credit_note_hub_number    ON credit_notes_note (hub_id, credit_note_number);
CREATE INDEX        IF NOT EXISTS ix_cn_hub_status             ON credit_notes_note (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_cn_hub_direction          ON credit_notes_note (hub_id, direction);
CREATE INDEX        IF NOT EXISTS ix_cn_hub_counterparty       ON credit_notes_note (hub_id, counterparty_name);
CREATE INDEX        IF NOT EXISTS ix_cn_hub_issue_date         ON credit_notes_note (hub_id, issue_date);
CREATE INDEX        IF NOT EXISTS idx_credit_notes_note_hub    ON credit_notes_note (hub_id, is_deleted);

-- Línea de la nota de abono.
CREATE TABLE IF NOT EXISTS credit_notes_line (
    id             TEXT PRIMARY KEY,
    hub_id         TEXT NOT NULL,
    credit_note_id TEXT NOT NULL,
    description    TEXT NOT NULL,
    quantity       NUMERIC NOT NULL DEFAULT 1,
    unit_price     NUMERIC NOT NULL DEFAULT 0,
    line_total     NUMERIC NOT NULL DEFAULT 0,          -- quantity * unit_price
    tax_rate       NUMERIC NOT NULL DEFAULT 0,
    is_deleted     INTEGER NOT NULL DEFAULT 0,
    deleted_at     TEXT,
    created_by     TEXT,
    updated_by     TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT,
    FOREIGN KEY (credit_note_id) REFERENCES credit_notes_note (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_cnl_hub_credit_note     ON credit_notes_line (hub_id, credit_note_id);
CREATE INDEX IF NOT EXISTS idx_credit_notes_line_hub  ON credit_notes_line (hub_id, is_deleted);

-- Aplicación de la nota contra una factura (parcial o total).
CREATE TABLE IF NOT EXISTS credit_notes_application (
    id             TEXT PRIMARY KEY,
    hub_id         TEXT NOT NULL,
    credit_note_id TEXT NOT NULL,
    invoice_ref    TEXT NOT NULL,                        -- ref suelta de factura (sin FK)
    amount_applied NUMERIC NOT NULL,
    applied_at     TEXT NOT NULL,
    is_deleted     INTEGER NOT NULL DEFAULT 0,
    deleted_at     TEXT,
    created_by     TEXT,
    updated_by     TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT,
    FOREIGN KEY (credit_note_id) REFERENCES credit_notes_note (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_cna_hub_credit_note        ON credit_notes_application (hub_id, credit_note_id);
CREATE INDEX IF NOT EXISTS ix_cna_hub_invoice_ref        ON credit_notes_application (hub_id, invoice_ref);
CREATE INDEX IF NOT EXISTS idx_credit_notes_application_hub ON credit_notes_application (hub_id, is_deleted);

-- Contador atómico por (hub, día) para generar credit_note_number (CN-YYYYMMDD-NNNN).
-- Se actualiza vía upsert (INSERT ... ON CONFLICT DO UPDATE ... RETURNING) — sin SELECT/UPDATE.
CREATE TABLE IF NOT EXISTS credit_notes_counter (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    day         TEXT NOT NULL,                            -- YYYYMMDD
    last_number INTEGER NOT NULL DEFAULT 0,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_credit_note_counter_hub_day ON credit_notes_counter (hub_id, day);
CREATE INDEX        IF NOT EXISTS idx_credit_notes_counter_hub   ON credit_notes_counter (hub_id, is_deleted);
