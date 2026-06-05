-- Banking · esquema inicial (SQLite). Portado fielmente de old_modules/m_banking/models.py.
-- Modelos: BankAccount (cuenta bancaria del hub), BankTransaction (apunte del libro mayor,
-- importe con signo: + entrada / - salida) y BankReconciliation (sesión de conciliación de
-- extracto contra una cuenta). Contrato de fila estándar de hub-next (§2.5): hub_id +
-- soft-delete (is_deleted/deleted_at) + auditoría (created_by/updated_by/created_at/updated_at).

-- Cuenta bancaria. iban es único por hub. current_balance es un saldo cacheado que se
-- mantiene al añadir apuntes (lógica en WASM — ver WASM-TODO); opening_balance es el saldo
-- inicial inmutable. El invariant banking.balance_matches_movements verifica la consistencia.
CREATE TABLE IF NOT EXISTS banking_account (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    name            TEXT NOT NULL,
    iban            TEXT NOT NULL,
    bic             TEXT NOT NULL DEFAULT '',
    currency        TEXT NOT NULL DEFAULT 'EUR',   -- ISO 4217 (3 letras)
    opening_balance NUMERIC NOT NULL DEFAULT 0,     -- saldo inicial (inmutable)
    current_balance NUMERIC NOT NULL DEFAULT 0,     -- saldo cacheado (= opening + Σ apuntes)
    is_active       INTEGER NOT NULL DEFAULT 1,
    notes           TEXT NOT NULL DEFAULT '',
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_banking_account_hub_iban   ON banking_account (hub_id, iban);
CREATE INDEX        IF NOT EXISTS ix_banking_account_hub_active ON banking_account (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS idx_banking_account_hub       ON banking_account (hub_id, is_deleted);

-- Apunte bancario ligado a una cuenta. amount con signo (+ entrada / - salida).
-- source ∈ (manual|import|api). is_reconciled marca si está conciliado contra extracto.
CREATE TABLE IF NOT EXISTS banking_transaction (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    account_id       TEXT NOT NULL,
    transaction_date TEXT NOT NULL,                  -- ISO YYYY-MM-DD
    value_date       TEXT,                           -- ISO YYYY-MM-DD o NULL (fecha valor)
    amount           NUMERIC NOT NULL,               -- con signo: + entrada / - salida
    description      TEXT NOT NULL DEFAULT '',
    counterparty     TEXT NOT NULL DEFAULT '',
    reference        TEXT NOT NULL DEFAULT '',
    is_reconciled    INTEGER NOT NULL DEFAULT 0,
    reconciled_at    TEXT,                            -- ISO timestamp o NULL
    source           TEXT NOT NULL DEFAULT 'manual',  -- manual|import|api
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT,
    FOREIGN KEY (account_id) REFERENCES banking_account (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_banking_tx_hub_account    ON banking_transaction (hub_id, account_id);
CREATE INDEX IF NOT EXISTS ix_banking_tx_hub_date       ON banking_transaction (hub_id, transaction_date);
CREATE INDEX IF NOT EXISTS ix_banking_tx_hub_reconciled ON banking_transaction (hub_id, is_reconciled);
CREATE INDEX IF NOT EXISTS idx_banking_transaction_hub  ON banking_transaction (hub_id, is_deleted);

-- Sesión de conciliación de extracto para una cuenta. status ∈ (open|closed).
-- statement_balance = saldo según el extracto del banco a statement_date.
CREATE TABLE IF NOT EXISTS banking_reconciliation (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    account_id        TEXT NOT NULL,
    statement_date    TEXT NOT NULL,                 -- ISO YYYY-MM-DD
    statement_balance NUMERIC NOT NULL DEFAULT 0,
    status            TEXT NOT NULL DEFAULT 'open',  -- open|closed
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    FOREIGN KEY (account_id) REFERENCES banking_account (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_banking_recon_hub_account ON banking_reconciliation (hub_id, account_id);
CREATE INDEX IF NOT EXISTS ix_banking_recon_hub_status  ON banking_reconciliation (hub_id, status);
CREATE INDEX IF NOT EXISTS idx_banking_reconciliation_hub ON banking_reconciliation (hub_id, is_deleted);
