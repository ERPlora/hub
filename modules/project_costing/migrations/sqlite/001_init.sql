-- Project Costing · esquema inicial (SQLite). Portado fielmente de
-- old_modules/m_project_costing/models.py.
-- Modelos: ProjectBudget (sobre de gasto aprobado por proyecto/año fiscal),
-- CostEntry (coste individual imputado a un proyecto) y CostCategory
-- (taxonomía jerárquica de categorías de coste, código único por hub).
-- Las referencias a otros dominios (proyecto, empleado, proveedor) son strings
-- libres (project_ref/employee_ref/supplier_ref) para no acoplar a otros módulos.
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Presupuesto de proyecto: importe aprobado para un proyecto en un año fiscal.
-- Ciclo de vida del status: draft → active → closed.
CREATE TABLE IF NOT EXISTS project_costing_budget (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    project_ref      TEXT NOT NULL,                 -- referencia libre al proyecto
    budget_amount    NUMERIC NOT NULL DEFAULT 0,
    currency         TEXT NOT NULL DEFAULT 'EUR',
    fiscal_year      INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'draft',  -- draft|active|closed
    approved_by_ref  TEXT NOT NULL DEFAULT '',
    approved_at      TEXT,                           -- ISO datetime o NULL
    notes            TEXT NOT NULL DEFAULT '',
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT
);
CREATE INDEX IF NOT EXISTS ix_pc_budget_hub_project ON project_costing_budget (hub_id, project_ref);
CREATE INDEX IF NOT EXISTS ix_pc_budget_hub_status  ON project_costing_budget (hub_id, status);
CREATE INDEX IF NOT EXISTS idx_project_costing_budget_hub ON project_costing_budget (hub_id, is_deleted);

-- Entrada de coste: coste concreto imputado a un proyecto.
-- Ciclo de vida del status: pending → approved | rejected.
CREATE TABLE IF NOT EXISTS project_costing_entry (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    project_ref   TEXT NOT NULL,                     -- referencia libre al proyecto
    entry_date    TEXT,                              -- ISO YYYY-MM-DD o NULL
    cost_type     TEXT NOT NULL DEFAULT 'expense',   -- labor|material|expense|subcontract|overhead
    description   TEXT NOT NULL DEFAULT '',
    amount        NUMERIC NOT NULL DEFAULT 0,
    hours         NUMERIC,                           -- horas imputadas (opcional)
    employee_ref  TEXT NOT NULL DEFAULT '',          -- referencia libre al empleado
    supplier_ref  TEXT NOT NULL DEFAULT '',          -- referencia libre al proveedor
    status        TEXT NOT NULL DEFAULT 'pending',   -- pending|approved|rejected
    notes         TEXT NOT NULL DEFAULT '',
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT
);
CREATE INDEX IF NOT EXISTS ix_pc_entry_hub_project ON project_costing_entry (hub_id, project_ref);
CREATE INDEX IF NOT EXISTS ix_pc_entry_hub_status  ON project_costing_entry (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_pc_entry_hub_type    ON project_costing_entry (hub_id, cost_type);
CREATE INDEX IF NOT EXISTS ix_pc_entry_hub_date    ON project_costing_entry (hub_id, entry_date);
CREATE INDEX IF NOT EXISTS idx_project_costing_entry_hub ON project_costing_entry (hub_id, is_deleted);

-- Categoría de coste: taxonomía jerárquica (parent opcional), código único por hub.
CREATE TABLE IF NOT EXISTS project_costing_category (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    code        TEXT NOT NULL,
    name        TEXT NOT NULL,
    parent_id   TEXT,                                -- FK a sí misma (jerarquía), NULL = raíz
    is_active   INTEGER NOT NULL DEFAULT 1,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT,
    FOREIGN KEY (parent_id) REFERENCES project_costing_category (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pc_category_hub_code   ON project_costing_category (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_pc_category_hub_parent ON project_costing_category (hub_id, parent_id);
CREATE INDEX        IF NOT EXISTS idx_project_costing_category_hub ON project_costing_category (hub_id, is_deleted);
