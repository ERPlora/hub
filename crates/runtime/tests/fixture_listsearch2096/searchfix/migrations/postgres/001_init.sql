-- hub#2096 fixture: names written the way a front desk stores them — capitalised and with
-- Spanish accents — next to a neighbour that must NOT match, and a numeric phone column that
-- proves the fold does not break searching over a non-text column. `name` is `COLLATE "C"` on
-- purpose: under the C collation `lower()` only knows ASCII (`lower('Í')` stays `'Í'`), the
-- worst case a hub's database can be created with, so the fold must not lean on `lower()`.
CREATE TABLE searchfix_customer (
  id TEXT PRIMARY KEY,
  hub_id TEXT NOT NULL,
  name TEXT COLLATE "C" NOT NULL,
  phone BIGINT NOT NULL,
  city TEXT NOT NULL
);
INSERT INTO searchfix_customer (id, hub_id, name, phone, city) VALUES
  ('marta',  'h1', 'Marta García',  600111222, 'Málaga'),
  ('ivan',   'h1', 'IVÁN NÚÑEZ',    600333444, 'Ávila'),
  ('pedro',  'h1', 'Pedro López',   600555666, 'Madrid'),
  ('other',  'h2', 'Otra García',   600777888, 'Málaga');
