CREATE TABLE IF NOT EXISTS dberr_topic (
    id TEXT PRIMARY KEY, hub_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS dberr_note (
    id TEXT PRIMARY KEY, hub_id TEXT NOT NULL,
    topic_id TEXT NOT NULL REFERENCES dberr_topic (id),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
