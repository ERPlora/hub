CREATE TABLE IF NOT EXISTS inventory_product (
    id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, name TEXT NOT NULL, sku TEXT,
    price REAL NOT NULL DEFAULT 0, stock REAL NOT NULL DEFAULT 0,
    is_deleted INTEGER NOT NULL DEFAULT 0, created_by TEXT, updated_by TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_products_hub ON inventory_product (hub_id, is_deleted);
