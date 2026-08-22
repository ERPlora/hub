-- hub#1086 fixture: two lists — one whose base SQL NEEDS a context bind (:cart_id),
-- one whose optional bind is COALESCE-guarded (:include_archived, the services#44 idiom).
CREATE TABLE lbind_cart (
  id TEXT PRIMARY KEY,
  hub_id TEXT NOT NULL,
  name TEXT NOT NULL,
  archived INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE lbind_item (
  id TEXT PRIMARY KEY,
  hub_id TEXT NOT NULL,
  cart_id TEXT NOT NULL,
  name TEXT NOT NULL
);
INSERT INTO lbind_cart (id, hub_id, name, archived) VALUES
  ('cart-a', 'h1', 'Cart A', 0),
  ('cart-b', 'h1', 'Cart B', 0),
  ('cart-old', 'h1', 'Archived cart', 1);
INSERT INTO lbind_item (id, hub_id, cart_id, name) VALUES
  ('i1', 'h1', 'cart-a', 'coffee'),
  ('i2', 'h1', 'cart-a', 'croissant'),
  ('i3', 'h1', 'cart-a', 'orange juice'),
  ('i4', 'h1', 'cart-b', 'sandwich');
