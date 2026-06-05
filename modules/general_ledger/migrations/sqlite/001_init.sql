-- General Ledger · esquema inicial (SQLite). Portado fielmente de
-- old_modules/m_general_ledger/models.py.
-- Modelos: GLAccount (plan contable extendido), CostCenter (dimensión analítica),
-- LedgerPeriod (periodo fiscal con cierre), LedgerEntry (asiento cabecera),
-- LedgerLine (apunte con eje de centro de coste) y LedgerEntryCounter (secuencia atómica).
-- Independiente de m_accounting: tablas propias general_ledger_*.
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Cuenta del plan contable extendido. code único por hub. parent_id permite jerarquía
-- (auto-FK). is_summary marca nodos agregadores: no se puede asentar directamente sobre ellos.
-- normal_balance (debit|credit) lo infiere el servicio a partir de account_type.
CREATE TABLE IF NOT EXISTS general_ledger_account (
    id             TEXT PRIMARY KEY,
    hub_id         TEXT NOT NULL,
    code           TEXT NOT NULL,
    name           TEXT NOT NULL,
    account_type   TEXT NOT NULL,                 -- asset|liability|equity|income|expense
    normal_balance TEXT NOT NULL DEFAULT 'debit', -- debit|credit
    parent_id      TEXT,                          -- auto-FK; NULL para raíces
    is_summary     INTEGER NOT NULL DEFAULT 0,
    is_active      INTEGER NOT NULL DEFAULT 1,
    currency       TEXT NOT NULL DEFAULT 'EUR',
    is_deleted     INTEGER NOT NULL DEFAULT 0,
    deleted_at     TEXT,
    created_by     TEXT,
    updated_by     TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT,
    FOREIGN KEY (parent_id) REFERENCES general_ledger_account (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_gl_account_hub_code  ON general_ledger_account (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_gl_account_hub_type   ON general_ledger_account (hub_id, account_type);
CREATE INDEX        IF NOT EXISTS ix_gl_account_hub_parent ON general_ledger_account (hub_id, parent_id);
CREATE INDEX        IF NOT EXISTS idx_general_ledger_account_hub ON general_ledger_account (hub_id, is_deleted);

-- Centro de coste: dimensión analítica (managerial). Forma árbol (parent_id auto-FK)
-- para que los informes puedan agregar hijos en padres. code único por hub.
CREATE TABLE IF NOT EXISTS general_ledger_cost_center (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    code        TEXT NOT NULL,
    name        TEXT NOT NULL,
    parent_id   TEXT,                              -- auto-FK; NULL para raíces
    is_active   INTEGER NOT NULL DEFAULT 1,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT,
    FOREIGN KEY (parent_id) REFERENCES general_ledger_cost_center (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_gl_cost_center_hub_code   ON general_ledger_cost_center (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_gl_cost_center_hub_parent ON general_ledger_cost_center (hub_id, parent_id);
CREATE INDEX        IF NOT EXISTS idx_general_ledger_cost_center_hub ON general_ledger_cost_center (hub_id, is_deleted);

-- Periodo de asiento (típicamente un mes) que se puede cerrar. status open|closed.
-- Con status='closed' el servicio rechaza asentar/revertir asientos dentro de la ventana.
-- name único por hub. closed_by_ref guarda quién cerró (referencia textual).
CREATE TABLE IF NOT EXISTS general_ledger_period (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    name          TEXT NOT NULL,
    start_date    TEXT NOT NULL,                   -- ISO YYYY-MM-DD
    end_date      TEXT NOT NULL,                   -- ISO YYYY-MM-DD
    status        TEXT NOT NULL DEFAULT 'open',    -- open|closed
    closed_at     TEXT,
    closed_by_ref TEXT NOT NULL DEFAULT '',
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_gl_period_hub_name   ON general_ledger_period (hub_id, name);
CREATE INDEX        IF NOT EXISTS ix_gl_period_hub_dates   ON general_ledger_period (hub_id, start_date, end_date);
CREATE INDEX        IF NOT EXISTS ix_gl_period_hub_status  ON general_ledger_period (hub_id, status);
CREATE INDEX        IF NOT EXISTS idx_general_ledger_period_hub ON general_ledger_period (hub_id, is_deleted);

-- Cabecera de asiento balanceado (sum(debits) == sum(credits)). entry_number único por hub.
-- status draft|posted|reversed. total_debit/total_credit son cacheados de las líneas.
CREATE TABLE IF NOT EXISTS general_ledger_entry (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    entry_number  TEXT NOT NULL,
    entry_date    TEXT NOT NULL,                   -- ISO YYYY-MM-DD
    period_id     TEXT NOT NULL,
    reference     TEXT NOT NULL DEFAULT '',
    description   TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'draft',   -- draft|posted|reversed
    total_debit   NUMERIC NOT NULL DEFAULT 0,
    total_credit  NUMERIC NOT NULL DEFAULT 0,
    posted_at     TEXT,
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT,
    FOREIGN KEY (period_id) REFERENCES general_ledger_period (id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_gl_entry_hub_number  ON general_ledger_entry (hub_id, entry_number);
CREATE INDEX        IF NOT EXISTS ix_gl_entry_hub_period   ON general_ledger_entry (hub_id, period_id);
CREATE INDEX        IF NOT EXISTS ix_gl_entry_hub_date     ON general_ledger_entry (hub_id, entry_date);
CREATE INDEX        IF NOT EXISTS ix_gl_entry_hub_status   ON general_ledger_entry (hub_id, status);
CREATE INDEX        IF NOT EXISTS idx_general_ledger_entry_hub ON general_ledger_entry (hub_id, is_deleted);

-- Apunte: un lado de un asiento. Exactamente uno de debit/credit es no-cero (el servicio
-- lo garantiza). cost_center_id es el eje analítico opcional (NULL = no analítico).
CREATE TABLE IF NOT EXISTS general_ledger_line (
    id             TEXT PRIMARY KEY,
    hub_id         TEXT NOT NULL,
    entry_id       TEXT NOT NULL,
    account_id     TEXT NOT NULL,
    cost_center_id TEXT,                           -- opcional
    debit          NUMERIC NOT NULL DEFAULT 0,
    credit         NUMERIC NOT NULL DEFAULT 0,
    description    TEXT NOT NULL DEFAULT '',
    is_deleted     INTEGER NOT NULL DEFAULT 0,
    deleted_at     TEXT,
    created_by     TEXT,
    updated_by     TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT,
    FOREIGN KEY (entry_id)       REFERENCES general_ledger_entry (id) ON DELETE CASCADE,
    FOREIGN KEY (account_id)     REFERENCES general_ledger_account (id) ON DELETE RESTRICT,
    FOREIGN KEY (cost_center_id) REFERENCES general_ledger_cost_center (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_gl_line_hub_entry       ON general_ledger_line (hub_id, entry_id);
CREATE INDEX IF NOT EXISTS ix_gl_line_hub_account     ON general_ledger_line (hub_id, account_id);
CREATE INDEX IF NOT EXISTS ix_gl_line_hub_cost_center ON general_ledger_line (hub_id, cost_center_id);
CREATE INDEX IF NOT EXISTS idx_general_ledger_line_hub ON general_ledger_line (hub_id, is_deleted);

-- Contador atómico de nº de asiento por (hub, año). Patrón UPSERT
-- (INSERT ... ON CONFLICT DO UPDATE ... RETURNING) para que el incremento sea
-- race-free en SQLite y Postgres. Lo gestiona el runtime/WASM, no la UI.
CREATE TABLE IF NOT EXISTS general_ledger_entry_counter (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    year        INTEGER NOT NULL,
    last_number INTEGER NOT NULL DEFAULT 0,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_gl_entry_counter_hub_year ON general_ledger_entry_counter (hub_id, year);
CREATE INDEX        IF NOT EXISTS idx_general_ledger_entry_counter_hub ON general_ledger_entry_counter (hub_id, is_deleted);
