CREATE TABLE IF NOT EXISTS slowtill_sales (
    id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, label TEXT NOT NULL,
    created_by TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_slowtill_sales_hub ON slowtill_sales (hub_id);
-- hub#1680: arrivals, OUTSIDE any transaction. A sequence is the one thing a command in flight can
-- see another command in flight write: rows stay invisible until commit, `nextval` does not.
CREATE SEQUENCE IF NOT EXISTS slowtill_arrivals;
-- …and departures: «in flight» is arrivals minus departures, not «somebody arrived once».
CREATE SEQUENCE IF NOT EXISTS slowtill_departures;
