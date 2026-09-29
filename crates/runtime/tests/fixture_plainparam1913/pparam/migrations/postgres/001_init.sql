-- hub#1913 fixture: one table read by a PLAIN query (no `list` block).
CREATE TABLE pparam_item (
  id TEXT PRIMARY KEY,
  hub_id TEXT NOT NULL,
  name TEXT NOT NULL
);
INSERT INTO pparam_item (id, hub_id, name) VALUES
  ('i1', 'h1', 'coffee'),
  ('i2', 'h2', 'tea');
