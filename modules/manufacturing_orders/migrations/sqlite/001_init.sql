-- Manufacturing Orders · esquema inicial (SQLite). Portado fielmente de
-- old_modules/m_manufacturing_orders/models.py.
-- Modelos: ManufacturingOrder (orden de producción), MaterialConsumption
-- (consumo de materia prima planificado vs real) y ManufacturingOrderCounter
-- (contador atómico por hub+día para generar mo_number).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Orden de fabricación: producir quantity_planned de product_ref.
-- mo_number = MO-YYYYMMDD-NNNN, único por hub. Ciclo de vida:
-- draft -> released -> in_progress -> completed | cancelled.
CREATE TABLE IF NOT EXISTS manufacturing_orders_order (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    mo_number         TEXT NOT NULL,                       -- MO-YYYYMMDD-NNNN (contador atómico)
    product_ref       TEXT NOT NULL,                       -- ref libre del producto a fabricar
    quantity_planned  NUMERIC NOT NULL DEFAULT 0,
    quantity_produced NUMERIC NOT NULL DEFAULT 0,
    scheduled_date    TEXT,                                -- ISO YYYY-MM-DD | NULL
    due_date          TEXT,                                -- ISO YYYY-MM-DD | NULL
    status            TEXT NOT NULL DEFAULT 'draft',       -- draft|released|in_progress|completed|cancelled
    priority          TEXT NOT NULL DEFAULT 'normal',      -- low|normal|high|urgent
    work_center_ref   TEXT NOT NULL DEFAULT '',            -- ref opcional de centro/línea de trabajo
    notes             TEXT NOT NULL DEFAULT '',
    started_at        TEXT,                                -- ISO datetime | NULL (al pasar a in_progress)
    completed_at      TEXT,                                -- ISO datetime | NULL (al pasar a completed)
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT
);
CREATE INDEX        IF NOT EXISTS idx_manufacturing_orders_order_hub ON manufacturing_orders_order (hub_id, is_deleted);
CREATE INDEX        IF NOT EXISTS ix_mo_hub_status                   ON manufacturing_orders_order (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_mo_hub_product                  ON manufacturing_orders_order (hub_id, product_ref);
CREATE INDEX        IF NOT EXISTS ix_mo_hub_scheduled                ON manufacturing_orders_order (hub_id, scheduled_date);
CREATE UNIQUE INDEX IF NOT EXISTS uq_mo_hub_number                   ON manufacturing_orders_order (hub_id, mo_number);

-- Consumo de material: materia prima planificada y realmente consumida por orden.
-- status: pending -> consumed (si consumido >= planificado) | short (si < planificado).
CREATE TABLE IF NOT EXISTS manufacturing_orders_material (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    mo_id             TEXT NOT NULL,                       -- FK a manufacturing_orders_order
    material_ref      TEXT NOT NULL,                       -- ref libre del material
    quantity_planned  NUMERIC NOT NULL DEFAULT 0,
    quantity_consumed NUMERIC NOT NULL DEFAULT 0,
    unit              TEXT NOT NULL DEFAULT 'unit',
    status            TEXT NOT NULL DEFAULT 'pending',     -- pending|consumed|short
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    FOREIGN KEY (mo_id) REFERENCES manufacturing_orders_order (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_manufacturing_orders_material_hub ON manufacturing_orders_material (hub_id, is_deleted);
CREATE INDEX IF NOT EXISTS ix_mo_material_hub_mo                 ON manufacturing_orders_material (hub_id, mo_id);
CREATE INDEX IF NOT EXISTS ix_mo_material_hub_status             ON manufacturing_orders_material (hub_id, status);

-- Contador atómico por (hub, día) para generar mo_number sin carrera.
-- Se escribe vía UPSERT (INSERT ... ON CONFLICT DO UPDATE ... RETURNING) en el runtime.
CREATE TABLE IF NOT EXISTS manufacturing_orders_counter (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    day          TEXT NOT NULL,                            -- YYYYMMDD
    last_number  INTEGER NOT NULL DEFAULT 0,
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT
);
CREATE INDEX        IF NOT EXISTS idx_manufacturing_orders_counter_hub ON manufacturing_orders_counter (hub_id, is_deleted);
CREATE UNIQUE INDEX IF NOT EXISTS uq_mo_counter_hub_day                ON manufacturing_orders_counter (hub_id, day);
