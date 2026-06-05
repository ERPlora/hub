-- Accounting · esquema inicial (SQLite). Portado fielmente de old_modules/m_accounting/models.py.
-- Modelos: Account (plan de cuentas en árbol), JournalEntry (asiento contable cabecera),
-- JournalLine (apunte/línea: debe o haber), FiscalYear (ejercicio fiscal acotado) y
-- EntryCounter (contador atómico de nº de asiento por hub+año).
-- Contabilidad por partida doble: cada JournalEntry tiene varias JournalLines cuyos
-- débitos y créditos deben sumar el mismo total. Contabilizar (post) un asiento es una
-- transición atómica draft→posted; cancelar un asiento contabilizado genera un contra-asiento
-- (nunca borra el original — rastro fiscal). Esa lógica vive en WASM (ver WASM-TODO.md).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Cuenta del plan contable. code es la clave humana (p.ej. "1000" para caja) y es única
-- por hub. parent_id es auto-FK que permite formar un árbol ("1"→"10"→"1000").
-- normal_balance es el lado en el que se acumula el saldo (debit|credit).
-- account_type: asset|liability|equity|income|expense.
CREATE TABLE IF NOT EXISTS accounting_account (
    id             TEXT PRIMARY KEY,
    hub_id         TEXT NOT NULL,
    code           TEXT NOT NULL,
    name           TEXT NOT NULL,
    account_type   TEXT NOT NULL,                  -- asset|liability|equity|income|expense
    parent_id      TEXT,                           -- auto-FK (árbol de cuentas)
    is_active      INTEGER NOT NULL DEFAULT 1,
    normal_balance TEXT NOT NULL DEFAULT 'debit',  -- debit|credit
    is_deleted     INTEGER NOT NULL DEFAULT 0,
    deleted_at     TEXT,
    created_by     TEXT,
    updated_by     TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT,
    FOREIGN KEY (parent_id) REFERENCES accounting_account (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_account_hub_code      ON accounting_account (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_account_hub_type      ON accounting_account (hub_id, account_type);
CREATE INDEX        IF NOT EXISTS ix_account_hub_parent    ON accounting_account (hub_id, parent_id);
CREATE INDEX        IF NOT EXISTS idx_accounting_account_hub ON accounting_account (hub_id, is_deleted);

-- Asiento contable (cabecera). Equilibrado: sum(debits) == sum(credits).
-- entry_number es único por (hub, año) y lo genera el contador atómico (ver WASM-TODO).
-- status: draft|posted|cancelled. posted_at/posted_by se rellenan al contabilizar.
CREATE TABLE IF NOT EXISTS accounting_journal_entry (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    entry_number  TEXT NOT NULL,
    entry_date    TEXT NOT NULL,                   -- ISO YYYY-MM-DD
    reference     TEXT NOT NULL DEFAULT '',
    description   TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'draft',   -- draft|posted|cancelled
    total_debit   NUMERIC NOT NULL DEFAULT 0,
    total_credit  NUMERIC NOT NULL DEFAULT 0,
    posted_at     TEXT,
    posted_by     TEXT,
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_journal_entry_hub_number ON accounting_journal_entry (hub_id, entry_number);
CREATE INDEX        IF NOT EXISTS ix_journal_entry_hub_date   ON accounting_journal_entry (hub_id, entry_date);
CREATE INDEX        IF NOT EXISTS ix_journal_entry_hub_status ON accounting_journal_entry (hub_id, status);
CREATE INDEX        IF NOT EXISTS idx_accounting_journal_entry_hub ON accounting_journal_entry (hub_id, is_deleted);

-- Apunte/línea: un lado del asiento. En una línea bien formada exactamente uno de
-- debit/credit es no-cero (lo garantiza el handler WASM, no la BD).
CREATE TABLE IF NOT EXISTS accounting_journal_line (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    entry_id     TEXT NOT NULL,
    account_id   TEXT NOT NULL,
    debit        NUMERIC NOT NULL DEFAULT 0,
    credit       NUMERIC NOT NULL DEFAULT 0,
    description  TEXT NOT NULL DEFAULT '',
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT,
    FOREIGN KEY (entry_id)   REFERENCES accounting_journal_entry (id) ON DELETE CASCADE,
    FOREIGN KEY (account_id) REFERENCES accounting_account (id)
);
CREATE INDEX IF NOT EXISTS ix_journal_line_hub_entry   ON accounting_journal_line (hub_id, entry_id);
CREATE INDEX IF NOT EXISTS ix_journal_line_hub_account ON accounting_journal_line (hub_id, account_id);
CREATE INDEX IF NOT EXISTS idx_accounting_journal_line_hub ON accounting_journal_line (hub_id, is_deleted);

-- Ejercicio fiscal: periodo contable acotado que puede cerrarse para bloquear apuntes.
-- name es único por hub.
CREATE TABLE IF NOT EXISTS accounting_fiscal_year (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    name        TEXT NOT NULL,
    start_date  TEXT NOT NULL,                     -- ISO YYYY-MM-DD
    end_date    TEXT NOT NULL,                     -- ISO YYYY-MM-DD
    is_closed   INTEGER NOT NULL DEFAULT 0,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fiscal_year_hub_name  ON accounting_fiscal_year (hub_id, name);
CREATE INDEX        IF NOT EXISTS ix_fiscal_year_hub_dates ON accounting_fiscal_year (hub_id, start_date, end_date);
CREATE INDEX        IF NOT EXISTS idx_accounting_fiscal_year_hub ON accounting_fiscal_year (hub_id, is_deleted);

-- Contador atómico de nº de asiento por (hub, año). Se escribe vía UPSERT
-- (INSERT ... ON CONFLICT DO UPDATE ... RETURNING) para que el incremento sea
-- una única ida-y-vuelta sin ventana SELECT/UPDATE. Lo invoca el handler WASM.
CREATE TABLE IF NOT EXISTS accounting_entry_counter (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    year         INTEGER NOT NULL,
    last_number  INTEGER NOT NULL DEFAULT 0,
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_entry_counter_hub_year ON accounting_entry_counter (hub_id, year);
CREATE INDEX        IF NOT EXISTS idx_accounting_entry_counter_hub ON accounting_entry_counter (hub_id, is_deleted);
