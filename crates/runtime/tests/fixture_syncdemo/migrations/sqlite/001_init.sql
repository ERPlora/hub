CREATE TABLE IF NOT EXISTS syncdemo_item (
  id TEXT PRIMARY KEY,
  hub_id TEXT NOT NULL,
  body TEXT,
  updated_at TEXT NOT NULL
);
