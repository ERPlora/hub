-- An inbox whose threads may not have a last activity yet (hub#2099).
CREATE TABLE IF NOT EXISTS nullsorder_thread (
  id              TEXT PRIMARY KEY,
  hub_id          TEXT NOT NULL,
  label           TEXT NOT NULL,
  last_message_at TIMESTAMPTZ NULL
);
