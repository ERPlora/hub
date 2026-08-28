-- inventory#7 (+ decimales de #10): libro de movimientos LOCATION-READY (ADR-0135).
-- Espejo de sqlite/005 — ver ahí el diseño completo. Diferencias de dialecto:
--   * cantidades REAL exactas (el decoder del hub las serializa como string);
--   * ALTER de `stock` a REAL en producto y variante (decimales, #10) —
--     en SQLite no hace falta ALTER (afinidad NUMERIC/INTEGER flexible).
CREATE TABLE IF NOT EXISTS inventory_location (
    id         TEXT PRIMARY KEY,
    hub_id     TEXT NOT NULL,
    name       TEXT NOT NULL DEFAULT 'General',
    is_default INTEGER NOT NULL DEFAULT 0,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    deleted_at TEXT,
    created_by TEXT,
    updated_by TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_inventory_location_default
    ON inventory_location (hub_id) WHERE is_default = 1;

CREATE TABLE IF NOT EXISTS inventory_stock_movement (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    location_id   TEXT NOT NULL,
    product_id    TEXT NOT NULL,
    movement_type TEXT NOT NULL,
    qty           REAL NOT NULL,
    stock_after   REAL NOT NULL,
    reason        TEXT,
    reference     TEXT,
    unit_cost     INTEGER,
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT,
    updated_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_ism_hub_product ON inventory_stock_movement (hub_id, product_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ism_hub_type    ON inventory_stock_movement (hub_id, movement_type);
CREATE INDEX IF NOT EXISTS idx_ism_hub_ref     ON inventory_stock_movement (hub_id, reference);

-- Decimales (#10): las existencias dejan de ser enteras.
ALTER TABLE inventory_product         ALTER COLUMN stock TYPE REAL;
ALTER TABLE inventory_product_variant ALTER COLUMN stock TYPE REAL;

INSERT INTO inventory_location (id, hub_id, name, is_default, is_deleted, created_at)
SELECT hub_id || ':default', hub_id, 'General', 1, 0, MIN(created_at)
FROM inventory_product WHERE is_deleted = 0
GROUP BY hub_id
ON CONFLICT (id) DO NOTHING;

INSERT INTO inventory_stock_movement
    (id, hub_id, location_id, product_id, movement_type, qty, stock_after, is_deleted, created_by, created_at)
SELECT id || ':initial', hub_id, hub_id || ':default', id, 'initial', stock, stock, 0, updated_by, updated_at
FROM inventory_product
WHERE is_deleted = 0 AND product_type != 'service' AND stock != 0
ON CONFLICT (id) DO NOTHING;
