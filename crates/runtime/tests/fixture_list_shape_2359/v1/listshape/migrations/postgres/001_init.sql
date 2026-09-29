-- hub#2359 fixture: the list's base SELECT is `SELECT *`, so its SHAPE (the columns it returns and
-- their types) belongs to the schema, not to the query text. v2 adds a column with an expand-only
-- migration and keeps the query file byte for byte: a remembered shape that outlived the update
-- would not know the new column.
CREATE TABLE listshape_item (
  id TEXT PRIMARY KEY,
  hub_id TEXT NOT NULL,
  priority INTEGER NOT NULL
);
INSERT INTO listshape_item (id, hub_id, priority) VALUES
  ('low',  'h1',   5),
  ('mid',  'h1',  20),
  ('high', 'h1', 100);
