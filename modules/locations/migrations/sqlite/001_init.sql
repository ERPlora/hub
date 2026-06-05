-- Locations · esquema inicial (SQLite). Portado fielmente de old_modules/m_locations/models.py.
-- Modelos: Warehouse (sitio físico) → Zone (agrupación por propósito) → Bin (ubicación
-- direccionable más pequeña) → StockPosition (cantidad de un producto/lote en un bin).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Almacén: sitio físico de nivel superior. code es único por hub. Solo una fila por hub
-- puede tener is_default=1 (invariant garantizado en runtime/WASM al crear con is_default).
CREATE TABLE IF NOT EXISTS locations_warehouse (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    code        TEXT NOT NULL,
    name        TEXT NOT NULL,
    address     TEXT NOT NULL DEFAULT '',
    is_active   INTEGER NOT NULL DEFAULT 1,
    is_default  INTEGER NOT NULL DEFAULT 0,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_locations_warehouse_hub_code   ON locations_warehouse (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_locations_warehouse_hub_active ON locations_warehouse (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS idx_locations_warehouse_hub       ON locations_warehouse (hub_id, is_deleted);

-- Zona: agrupación lógica de bins dentro de un almacén (p.ej. pasillo de picking).
-- code es único por (hub, warehouse). zone_type ∈ storage|picking|packing|receiving|shipping.
CREATE TABLE IF NOT EXISTS locations_zone (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    warehouse_id TEXT NOT NULL,
    code         TEXT NOT NULL,
    name         TEXT NOT NULL,
    zone_type    TEXT NOT NULL DEFAULT 'storage',   -- storage|picking|packing|receiving|shipping
    is_active    INTEGER NOT NULL DEFAULT 1,
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT,
    FOREIGN KEY (warehouse_id) REFERENCES locations_warehouse (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_locations_zone_wh_code        ON locations_zone (hub_id, warehouse_id, code);
CREATE INDEX        IF NOT EXISTS ix_locations_zone_hub_warehouse  ON locations_zone (hub_id, warehouse_id);
CREATE INDEX        IF NOT EXISTS ix_locations_zone_hub_type       ON locations_zone (hub_id, zone_type);
CREATE INDEX        IF NOT EXISTS idx_locations_zone_hub           ON locations_zone (hub_id, is_deleted);

-- Bin: ubicación direccionable más pequeña (estante/hueco). code es único dentro del
-- almacén (warehouse_id denormalizado para que el índice único funcione sin join).
-- is_blocked/block_reason permiten sacar un bin de circulación (dañado, mantenimiento).
CREATE TABLE IF NOT EXISTS locations_bin (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    zone_id      TEXT NOT NULL,
    warehouse_id TEXT NOT NULL,
    code         TEXT NOT NULL,
    barcode      TEXT NOT NULL DEFAULT '',
    capacity     NUMERIC,                           -- NULL = sin límite declarado
    is_active    INTEGER NOT NULL DEFAULT 1,
    is_blocked   INTEGER NOT NULL DEFAULT 0,
    block_reason TEXT NOT NULL DEFAULT '',
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT,
    FOREIGN KEY (zone_id)      REFERENCES locations_zone (id)      ON DELETE CASCADE,
    FOREIGN KEY (warehouse_id) REFERENCES locations_warehouse (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_locations_bin_wh_code       ON locations_bin (hub_id, warehouse_id, code);
CREATE INDEX        IF NOT EXISTS ix_locations_bin_hub_zone      ON locations_bin (hub_id, zone_id);
CREATE INDEX        IF NOT EXISTS ix_locations_bin_hub_blocked   ON locations_bin (hub_id, is_blocked);
CREATE INDEX        IF NOT EXISTS idx_locations_bin_hub          ON locations_bin (hub_id, is_deleted);

-- Posición de stock: cantidad de un product_ref (y lote opcional) en un bin concreto.
-- Una fila por (bin, product_ref, lot_ref). lot_ref puede ser '' (sin lote). last_count_at
-- guarda cuándo se contó por última vez (recuentos periódicos).
CREATE TABLE IF NOT EXISTS locations_stock_position (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    bin_id        TEXT NOT NULL,
    product_ref   TEXT NOT NULL,
    lot_ref       TEXT NOT NULL DEFAULT '',
    quantity      NUMERIC NOT NULL DEFAULT 0,
    last_count_at TEXT,                              -- ISO timestamp o NULL
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT,
    FOREIGN KEY (bin_id) REFERENCES locations_bin (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_locations_stock_bin_product_lot ON locations_stock_position (hub_id, bin_id, product_ref, lot_ref);
CREATE INDEX        IF NOT EXISTS ix_locations_stock_hub_bin         ON locations_stock_position (hub_id, bin_id);
CREATE INDEX        IF NOT EXISTS ix_locations_stock_hub_product     ON locations_stock_position (hub_id, product_ref);
CREATE INDEX        IF NOT EXISTS idx_locations_stock_hub            ON locations_stock_position (hub_id, is_deleted);
