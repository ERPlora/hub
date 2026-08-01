CREATE TABLE IF NOT EXISTS assistant_fixture_items (
  id TEXT PRIMARY KEY,
  hub_id TEXT NOT NULL,
  name TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_assistant_fixture_hub_name
  ON assistant_fixture_items (hub_id, name);
