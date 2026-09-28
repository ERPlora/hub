-- A task list where most rows share the value they are sorted by (hub#2352).
CREATE TABLE IF NOT EXISTS tiebreak_task (
  id     TEXT PRIMARY KEY,
  hub_id TEXT NOT NULL,
  title  TEXT NOT NULL,
  status TEXT NOT NULL,
  note   TEXT NULL
);
