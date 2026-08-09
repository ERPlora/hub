CREATE TABLE IF NOT EXISTS fprov_record (
    id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_fprov_record_hub ON fprov_record (hub_id);
