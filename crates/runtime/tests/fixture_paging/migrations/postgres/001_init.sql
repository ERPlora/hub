-- A catalogue a handler PRELOADS whole (a `reads` block), not a screen the user pages through.
CREATE TABLE IF NOT EXISTS paging_row (
  id     TEXT PRIMARY KEY,
  hub_id TEXT NOT NULL,
  n      INTEGER NOT NULL
);
