-- hub#2383 fixture: one table read by PLAIN queries (no `list` block), two hubs.
CREATE TABLE pbind_item (
  id TEXT PRIMARY KEY,
  hub_id TEXT NOT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  tag TEXT,
  due TEXT
);
INSERT INTO pbind_item (id, hub_id, name, status, tag, due) VALUES
  ('i1', 'h1', 'coffee', 'open', 'hot', '2026-10-01'),
  ('i2', 'h1', 'tea', 'done', NULL, '2026-12-01'),
  ('i3', 'h2', 'juice', 'open', 'cold', '2026-10-01');
