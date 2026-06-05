-- Picking & Packing · esquema inicial (SQLite). Portado de old_modules/m_picking_packing/models.py.
-- Modelos: PickList (orden de preparación asignada a operario), PickLine (línea de pick por
-- producto/ubicación/lote), Package (unidad física de envío) + dos contadores atómicos
-- (PickCounter / PackageCounter) para numeración por (hub, día).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Lista de pick: orden de preparación de almacén asignada a un operario.
-- pick_number es único por hub (formato PL-YYYYMMDD-NNNN, generado por el contador).
-- order_ref / assigned_to_ref son referencias libres (sin FK cross-módulo a sales/auth).
CREATE TABLE IF NOT EXISTS picking_packing_pick_list (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    pick_number     TEXT NOT NULL,
    order_ref       TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'draft',   -- draft|in_progress|completed|cancelled
    assigned_to_ref TEXT NOT NULL DEFAULT '',
    started_at      TEXT,                            -- ISO8601 o NULL
    completed_at    TEXT,                            -- ISO8601 o NULL
    notes           TEXT NOT NULL DEFAULT '',
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pp_pick_number       ON picking_packing_pick_list (hub_id, pick_number);
CREATE INDEX        IF NOT EXISTS ix_pp_pick_hub_status   ON picking_packing_pick_list (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_pp_pick_hub_assigned ON picking_packing_pick_list (hub_id, assigned_to_ref);
CREATE INDEX        IF NOT EXISTS ix_pp_pick_hub_order    ON picking_packing_pick_list (hub_id, order_ref);
CREATE INDEX        IF NOT EXISTS idx_pp_pick_list_hub    ON picking_packing_pick_list (hub_id, is_deleted);

-- Línea de pick: producto + cantidad solicitada/preparada + ubicación/lote.
-- product_ref es referencia libre (SKU/código/UUID-as-string), sin FK cross-módulo a products.
CREATE TABLE IF NOT EXISTS picking_packing_pick_line (
    id                 TEXT PRIMARY KEY,
    hub_id             TEXT NOT NULL,
    pick_list_id       TEXT NOT NULL,
    product_ref        TEXT NOT NULL,
    quantity_requested NUMERIC NOT NULL DEFAULT 0,
    quantity_picked    NUMERIC NOT NULL DEFAULT 0,
    location_ref       TEXT NOT NULL DEFAULT '',
    lot_ref            TEXT NOT NULL DEFAULT '',
    is_complete        INTEGER NOT NULL DEFAULT 0,
    is_deleted         INTEGER NOT NULL DEFAULT 0,
    deleted_at         TEXT,
    created_by         TEXT,
    updated_by         TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT,
    FOREIGN KEY (pick_list_id) REFERENCES picking_packing_pick_list (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_pp_pick_line_list   ON picking_packing_pick_line (hub_id, pick_list_id);
CREATE INDEX IF NOT EXISTS idx_pp_pick_line_hub   ON picking_packing_pick_line (hub_id, is_deleted);

-- Paquete: unidad física de envío (caja/palet/bulto). package_number único por hub
-- (formato PKG-YYYYMMDD-NNNN). pick_list_ref es referencia libre opcional (un paquete
-- puede ensamblarse sin pick formal: devoluciones, muestras, ad-hoc).
-- dimensions se guarda como texto JSON (portable SQLite/Postgres).
CREATE TABLE IF NOT EXISTS picking_packing_package (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    package_number  TEXT NOT NULL,
    pick_list_ref   TEXT NOT NULL DEFAULT '',
    weight_kg       NUMERIC NOT NULL DEFAULT 0,
    dimensions      TEXT NOT NULL DEFAULT '',        -- JSON libre o ''
    tracking_number TEXT NOT NULL DEFAULT '',
    carrier         TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'open',    -- open|sealed|shipped|delivered|returned
    packed_at       TEXT,                            -- ISO8601 o NULL
    packed_by_ref   TEXT NOT NULL DEFAULT '',
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pp_package_number     ON picking_packing_package (hub_id, package_number);
CREATE INDEX        IF NOT EXISTS ix_pp_pkg_hub_status     ON picking_packing_package (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_pp_pkg_hub_pick_ref   ON picking_packing_package (hub_id, pick_list_ref);
CREATE INDEX        IF NOT EXISTS idx_pp_package_hub       ON picking_packing_package (hub_id, is_deleted);

-- Contador atómico de nº de pick por (hub, día). last_number se incrementa vía UPSERT
-- (INSERT ... ON CONFLICT DO UPDATE ... RETURNING) — invocado por el handler WASM/runtime.
CREATE TABLE IF NOT EXISTS picking_packing_pick_counter (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    day         TEXT NOT NULL,                       -- YYYYMMDD
    last_number INTEGER NOT NULL DEFAULT 0,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pp_pick_counter_hub_day ON picking_packing_pick_counter (hub_id, day);
CREATE INDEX        IF NOT EXISTS idx_pp_pick_counter_hub    ON picking_packing_pick_counter (hub_id, is_deleted);

-- Contador atómico de nº de paquete por (hub, día). Misma mecánica que pick_counter.
CREATE TABLE IF NOT EXISTS picking_packing_package_counter (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    day         TEXT NOT NULL,                       -- YYYYMMDD
    last_number INTEGER NOT NULL DEFAULT 0,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pp_package_counter_hub_day ON picking_packing_package_counter (hub_id, day);
CREATE INDEX        IF NOT EXISTS idx_pp_package_counter_hub    ON picking_packing_package_counter (hub_id, is_deleted);
