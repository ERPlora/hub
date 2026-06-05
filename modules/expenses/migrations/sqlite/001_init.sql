-- Expenses · esquema inicial (SQLite). Portado fielmente de old_modules/m_expenses/models.py.
-- Modelos: ExpenseCategory (categoría jerárquica, code único por hub) y Expense (gasto de
-- empresa con flujo de aprobación draft -> submitted -> approved | rejected).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Categoría de gasto: jerárquica (parent_id opcional, autoreferencia). code único por hub.
CREATE TABLE IF NOT EXISTS expenses_category (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    code        TEXT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    parent_id   TEXT,                          -- autoreferencia opcional (categoría padre)
    is_active   INTEGER NOT NULL DEFAULT 1,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_by  TEXT,
    updated_at  TEXT,
    FOREIGN KEY (parent_id) REFERENCES expenses_category (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_expenses_category_hub_code   ON expenses_category (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_expenses_category_hub_parent ON expenses_category (hub_id, parent_id);
CREATE INDEX        IF NOT EXISTS idx_expenses_category_hub       ON expenses_category (hub_id, is_deleted);

-- Gasto de empresa con flujo de aprobación simple.
-- status: draft | submitted | approved | rejected. approved_by es FK suelta al usuario
-- local (no se fuerza a nivel BD, igual que en el legacy).
CREATE TABLE IF NOT EXISTS expenses_expense (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    category_id      TEXT NOT NULL,
    description      TEXT NOT NULL,
    amount           NUMERIC NOT NULL DEFAULT 0,
    expense_date     TEXT NOT NULL,                  -- ISO YYYY-MM-DD
    supplier_name    TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'draft',  -- draft|submitted|approved|rejected
    notes            TEXT NOT NULL DEFAULT '',
    approved_by      TEXT,                            -- FK suelta a usuario local
    approved_at      TEXT,                            -- ISO timestamp o NULL
    rejection_reason TEXT NOT NULL DEFAULT '',
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_by       TEXT,
    updated_at       TEXT,
    FOREIGN KEY (category_id) REFERENCES expenses_category (id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS ix_expenses_expense_hub_status   ON expenses_expense (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_expenses_expense_hub_category ON expenses_expense (hub_id, category_id);
CREATE INDEX IF NOT EXISTS ix_expenses_expense_hub_date     ON expenses_expense (hub_id, expense_date);
CREATE INDEX IF NOT EXISTS idx_expenses_expense_hub         ON expenses_expense (hub_id, is_deleted);
