CREATE TABLE IF NOT EXISTS w140_items (
    id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', touched_at TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_w140_items_hub ON w140_items (hub_id);
