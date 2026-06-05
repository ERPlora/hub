-- MRP · esquema inicial (SQLite). Portado fielmente de old_modules/m_mrp/models.py.
-- Modelos: MRPRun (cabecera de una ejecución de planificación), MaterialRequirement
-- (requerimiento neto por producto calculado por un run) y ProcurementSuggestion
-- (sugerencia comprar/fabricar derivada de un requerimiento).
-- MRP es un módulo analítico: las referencias a otros módulos (productos, órdenes
-- de fabricación, pedidos de venta, proveedores, usuarios) son strings sueltos *_ref;
-- NO hay FK cruzadas a tablas de otros módulos (cada módulo OWNea sus tablas).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Cabecera de una ejecución de MRP. run_number es legible (MRP-YYYYMMDD-NNNN),
-- único por hub. status: running|completed|failed. total_* denormalizados para
-- listados rápidos. parameters es JSON libre (Text) con los parámetros de la corrida.
CREATE TABLE IF NOT EXISTS mrp_run (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    run_number          TEXT NOT NULL,
    run_date            TEXT NOT NULL,                 -- ISO YYYY-MM-DD
    horizon_days        INTEGER NOT NULL DEFAULT 30,
    status              TEXT NOT NULL DEFAULT 'running', -- running|completed|failed
    started_at          TEXT,                          -- ISO datetime o NULL
    completed_at        TEXT,                          -- ISO datetime o NULL
    total_requirements  INTEGER NOT NULL DEFAULT 0,
    total_suggestions   INTEGER NOT NULL DEFAULT 0,
    parameters          TEXT NOT NULL DEFAULT '',      -- JSON con horizon_days/demand_count/...
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_mrp_run_hub_run_number ON mrp_run (hub_id, run_number);
CREATE INDEX        IF NOT EXISTS ix_mrp_run_hub_status     ON mrp_run (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_mrp_run_hub_run_date   ON mrp_run (hub_id, run_date);
CREATE INDEX        IF NOT EXISTS idx_mrp_run_hub           ON mrp_run (hub_id, is_deleted);

-- Requerimiento neto por producto computado por un run.
-- product_ref / source_ref son referencias sueltas a otros módulos (no FK cruzada).
-- net_requirement = max(0, quantity_required - quantity_on_hand - quantity_on_order).
-- source_type: mo|sales_order|forecast.
CREATE TABLE IF NOT EXISTS mrp_requirement (
    id                 TEXT PRIMARY KEY,
    hub_id             TEXT NOT NULL,
    run_id             TEXT NOT NULL,
    product_ref        TEXT NOT NULL,
    required_date      TEXT,                           -- ISO YYYY-MM-DD o NULL
    quantity_required  NUMERIC NOT NULL DEFAULT 0,
    quantity_on_hand   NUMERIC NOT NULL DEFAULT 0,
    quantity_on_order  NUMERIC NOT NULL DEFAULT 0,
    net_requirement    NUMERIC NOT NULL DEFAULT 0,
    source_type        TEXT NOT NULL DEFAULT 'forecast', -- mo|sales_order|forecast
    source_ref         TEXT NOT NULL DEFAULT '',
    is_deleted         INTEGER NOT NULL DEFAULT 0,
    deleted_at         TEXT,
    created_by         TEXT,
    updated_by         TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT,
    FOREIGN KEY (run_id) REFERENCES mrp_run (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_mrp_req_hub_run     ON mrp_requirement (hub_id, run_id);
CREATE INDEX IF NOT EXISTS ix_mrp_req_hub_product ON mrp_requirement (hub_id, product_ref);
CREATE INDEX IF NOT EXISTS idx_mrp_requirement_hub ON mrp_requirement (hub_id, is_deleted);

-- Sugerencia de aprovisionamiento (comprar/fabricar) derivada de un requerimiento.
-- suggested_type: buy|make. status: pending|approved|rejected.
-- suggested_date = required_date - lead_time_days.
CREATE TABLE IF NOT EXISTS mrp_suggestion (
    id                      TEXT PRIMARY KEY,
    hub_id                  TEXT NOT NULL,
    run_id                  TEXT NOT NULL,
    related_requirement_id  TEXT,
    product_ref             TEXT NOT NULL,
    suggested_type          TEXT NOT NULL DEFAULT 'buy', -- buy|make
    quantity                NUMERIC NOT NULL DEFAULT 0,
    suggested_date          TEXT,                        -- ISO YYYY-MM-DD o NULL
    lead_time_days          INTEGER NOT NULL DEFAULT 0,
    status                  TEXT NOT NULL DEFAULT 'pending', -- pending|approved|rejected
    approved_by_ref         TEXT NOT NULL DEFAULT '',
    notes                   TEXT NOT NULL DEFAULT '',
    is_deleted              INTEGER NOT NULL DEFAULT 0,
    deleted_at              TEXT,
    created_by              TEXT,
    updated_by              TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT,
    FOREIGN KEY (run_id) REFERENCES mrp_run (id) ON DELETE CASCADE,
    FOREIGN KEY (related_requirement_id) REFERENCES mrp_requirement (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_mrp_sug_hub_run     ON mrp_suggestion (hub_id, run_id);
CREATE INDEX IF NOT EXISTS ix_mrp_sug_hub_status  ON mrp_suggestion (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_mrp_sug_hub_product ON mrp_suggestion (hub_id, product_ref);
CREATE INDEX IF NOT EXISTS idx_mrp_suggestion_hub ON mrp_suggestion (hub_id, is_deleted);
