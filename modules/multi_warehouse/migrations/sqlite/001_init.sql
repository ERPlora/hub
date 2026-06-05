-- Multi-Warehouse · esquema inicial (SQLite). Portado fielmente de
-- old_modules/m_multi_warehouse/models.py.
-- Modelos: WarehouseLite (almacén del hub), WarehouseTransfer (documento de
-- traslado entre dos almacenes) y TransferLine (línea de producto del traslado).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.
-- Las referencias a productos/lotes/organización son strings sueltos (*_ref) sin FK,
-- para que el módulo pueda instalarse sin el módulo inventory/locations.

-- Almacén del hub. code es único por hub. type ∈ main|secondary|store|dropship.
-- is_default: a lo sumo uno por hub (lo garantiza la lógica de comandos, no la BD).
CREATE TABLE IF NOT EXISTS multi_warehouse_warehouse (
    id                      TEXT PRIMARY KEY,
    hub_id                  TEXT NOT NULL,
    code                    TEXT NOT NULL,
    name                    TEXT NOT NULL,
    address                 TEXT NOT NULL DEFAULT '',
    type                    TEXT NOT NULL DEFAULT 'secondary',  -- main|secondary|store|dropship
    is_active               INTEGER NOT NULL DEFAULT 1,
    is_default              INTEGER NOT NULL DEFAULT 0,
    owner_organization_ref  TEXT NOT NULL DEFAULT '',           -- ref suelta (sin FK)
    is_deleted              INTEGER NOT NULL DEFAULT 0,
    deleted_at              TEXT,
    created_by              TEXT,
    updated_by              TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_mw_warehouse_hub_code   ON multi_warehouse_warehouse (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_mw_warehouse_hub_active ON multi_warehouse_warehouse (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS ix_mw_warehouse_hub_default ON multi_warehouse_warehouse (hub_id, is_default);
CREATE INDEX        IF NOT EXISTS idx_multi_warehouse_warehouse_hub ON multi_warehouse_warehouse (hub_id, is_deleted);

-- Documento de traslado entre dos almacenes. transfer_number único por hub
-- (formato WT-YYYYMMDD-NNNN, generado atómicamente en runtime — ver WASM-TODO).
-- status ∈ draft|in_transit|received|cancelled. Fechas en ISO YYYY-MM-DD o NULL.
CREATE TABLE IF NOT EXISTS multi_warehouse_transfer (
    id                        TEXT PRIMARY KEY,
    hub_id                    TEXT NOT NULL,
    transfer_number           TEXT NOT NULL,
    source_warehouse_id       TEXT NOT NULL,
    destination_warehouse_id  TEXT NOT NULL,
    status                    TEXT NOT NULL DEFAULT 'draft',    -- draft|in_transit|received|cancelled
    created_date              TEXT,                             -- ISO YYYY-MM-DD o NULL
    dispatched_date           TEXT,                             -- ISO YYYY-MM-DD o NULL
    received_date             TEXT,                             -- ISO YYYY-MM-DD o NULL
    carrier                   TEXT NOT NULL DEFAULT '',
    tracking_ref              TEXT NOT NULL DEFAULT '',
    notes                     TEXT NOT NULL DEFAULT '',
    is_deleted                INTEGER NOT NULL DEFAULT 0,
    deleted_at                TEXT,
    created_by                TEXT,
    updated_by                TEXT,
    created_at                TEXT NOT NULL,
    updated_at                TEXT,
    FOREIGN KEY (source_warehouse_id)      REFERENCES multi_warehouse_warehouse (id) ON DELETE RESTRICT,
    FOREIGN KEY (destination_warehouse_id) REFERENCES multi_warehouse_warehouse (id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_mw_transfer_hub_number  ON multi_warehouse_transfer (hub_id, transfer_number);
CREATE INDEX        IF NOT EXISTS ix_mw_transfer_hub_status  ON multi_warehouse_transfer (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_mw_transfer_hub_source  ON multi_warehouse_transfer (hub_id, source_warehouse_id);
CREATE INDEX        IF NOT EXISTS ix_mw_transfer_hub_dest    ON multi_warehouse_transfer (hub_id, destination_warehouse_id);
CREATE INDEX        IF NOT EXISTS idx_multi_warehouse_transfer_hub ON multi_warehouse_transfer (hub_id, is_deleted);

-- Línea de producto de un traslado. product_ref / lot_ref son strings sueltos (sin FK).
-- Cantidades con 3 decimales (NUMERIC). quantity_requested se fija al crear; las otras
-- dos se actualizan en dispatch/receive.
CREATE TABLE IF NOT EXISTS multi_warehouse_transfer_line (
    id                   TEXT PRIMARY KEY,
    hub_id               TEXT NOT NULL,
    transfer_id          TEXT NOT NULL,
    product_ref          TEXT NOT NULL,
    quantity_requested   NUMERIC NOT NULL DEFAULT 0,
    quantity_dispatched  NUMERIC NOT NULL DEFAULT 0,
    quantity_received    NUMERIC NOT NULL DEFAULT 0,
    lot_ref              TEXT NOT NULL DEFAULT '',
    is_deleted           INTEGER NOT NULL DEFAULT 0,
    deleted_at           TEXT,
    created_by           TEXT,
    updated_by           TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT,
    FOREIGN KEY (transfer_id) REFERENCES multi_warehouse_transfer (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_mw_transferline_hub_transfer    ON multi_warehouse_transfer_line (hub_id, transfer_id);
CREATE INDEX IF NOT EXISTS idx_multi_warehouse_transfer_line_hub ON multi_warehouse_transfer_line (hub_id, is_deleted);
