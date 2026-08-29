CREATE TABLE IF NOT EXISTS slowtill_sales (
    id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, label TEXT NOT NULL,
    created_by TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_slowtill_sales_hub ON slowtill_sales (hub_id);
