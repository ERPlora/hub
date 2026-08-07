CREATE TABLE IF NOT EXISTS till_sales (
    id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, label TEXT NOT NULL,
    created_by TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_till_sales_hub ON till_sales (hub_id);
