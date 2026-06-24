CREATE TABLE IF NOT EXISTS catalog_items (
    id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, name TEXT NOT NULL,
    is_deleted INTEGER NOT NULL DEFAULT 0, created_by TEXT, updated_by TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_catalog_items_hub ON catalog_items (hub_id, is_deleted);
