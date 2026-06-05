-- Bank Reconciliation · esquema inicial (SQLite). Portado fielmente de
-- old_modules/m_bank_reconciliation/models.py.
-- Modelos: BankStatement (extracto bancario por periodo), StatementLine (línea/movimiento
-- crudo del extracto) y ReconciliationMatch (conciliación de una línea contra un apunte
-- contable externo, referenciado por string libre — sin FK dura a banking/accounting).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Extracto bancario de un periodo. Contenedor de líneas. statement_number es único por hub.
-- status: draft → in_progress → closed. amounts en NUMERIC(15,2).
CREATE TABLE IF NOT EXISTS bank_reconciliation_statement (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    statement_number TEXT NOT NULL,
    bank_account_ref TEXT NOT NULL DEFAULT '',   -- ref libre a cuenta bancaria (sin FK)
    statement_date   TEXT,                        -- ISO YYYY-MM-DD o NULL
    period_start     TEXT,                        -- ISO YYYY-MM-DD o NULL
    period_end       TEXT,                        -- ISO YYYY-MM-DD o NULL
    opening_balance  NUMERIC NOT NULL DEFAULT 0,
    closing_balance  NUMERIC NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'draft',  -- draft|in_progress|closed
    notes            TEXT NOT NULL DEFAULT '',
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_bank_recon_stmt_number_per_hub ON bank_reconciliation_statement (hub_id, statement_number);
CREATE INDEX        IF NOT EXISTS ix_bank_recon_stmt_hub_status     ON bank_reconciliation_statement (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_bank_recon_stmt_hub_account    ON bank_reconciliation_statement (hub_id, bank_account_ref);
CREATE INDEX        IF NOT EXISTS ix_bank_recon_stmt_hub_date       ON bank_reconciliation_statement (hub_id, statement_date);
CREATE INDEX        IF NOT EXISTS idx_bank_reconciliation_statement_hub ON bank_reconciliation_statement (hub_id, is_deleted);

-- Línea/movimiento crudo dentro de un extracto. amount con signo: + = abono (entra),
-- - = cargo (sale). is_matched marca si está conciliada (la pone el runtime al crear match).
CREATE TABLE IF NOT EXISTS bank_reconciliation_line (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    statement_id     TEXT NOT NULL,
    transaction_date TEXT,                          -- ISO YYYY-MM-DD o NULL
    amount           NUMERIC NOT NULL DEFAULT 0,    -- con signo: + abono / - cargo
    description      TEXT NOT NULL DEFAULT '',
    counterparty     TEXT NOT NULL DEFAULT '',
    reference        TEXT NOT NULL DEFAULT '',
    is_matched       INTEGER NOT NULL DEFAULT 0,
    matched_at       TEXT,                          -- ISO datetime o NULL
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT,
    FOREIGN KEY (statement_id) REFERENCES bank_reconciliation_statement (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_bank_recon_line_statement   ON bank_reconciliation_line (statement_id);
CREATE INDEX IF NOT EXISTS ix_bank_recon_line_hub_matched ON bank_reconciliation_line (hub_id, is_matched);
CREATE INDEX IF NOT EXISTS ix_bank_recon_line_hub_date    ON bank_reconciliation_line (hub_id, transaction_date);
CREATE INDEX IF NOT EXISTS idx_bank_reconciliation_line_hub ON bank_reconciliation_line (hub_id, is_deleted);

-- Conciliación de una línea contra un apunte contable externo. ledger_entry_ref es string
-- libre (no FK) para no acoplarse a un módulo de contabilidad concreto. confidence_score
-- 0..1 (1.000 para manual, heurística para auto). match_type: auto|manual.
CREATE TABLE IF NOT EXISTS bank_reconciliation_match (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    statement_line_id TEXT NOT NULL,
    ledger_entry_ref  TEXT NOT NULL,
    amount_matched    NUMERIC NOT NULL DEFAULT 0,
    match_type        TEXT NOT NULL DEFAULT 'manual',  -- auto|manual
    confidence_score  NUMERIC NOT NULL DEFAULT 1.000,  -- 0.000 .. 1.000
    matched_by_ref    TEXT NOT NULL DEFAULT '',        -- ref libre a UUID de usuario
    notes             TEXT NOT NULL DEFAULT '',
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    FOREIGN KEY (statement_line_id) REFERENCES bank_reconciliation_line (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_bank_recon_match_line       ON bank_reconciliation_match (statement_line_id);
CREATE INDEX IF NOT EXISTS ix_bank_recon_match_hub_ledger ON bank_reconciliation_match (hub_id, ledger_entry_ref);
CREATE INDEX IF NOT EXISTS idx_bank_reconciliation_match_hub ON bank_reconciliation_match (hub_id, is_deleted);
