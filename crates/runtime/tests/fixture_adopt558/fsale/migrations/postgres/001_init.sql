CREATE TABLE IF NOT EXISTS fsale_sale (
    id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, total TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_fsale_sale_hub ON fsale_sale (hub_id);
