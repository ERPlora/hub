-- A test app for hub#2485: it owns notes, and nothing else.
CREATE TABLE IF NOT EXISTS intruder_note (
    id     TEXT PRIMARY KEY,
    hub_id TEXT NOT NULL,
    body   TEXT NOT NULL DEFAULT ''
);
-- What the app heard: one row per `customer.anonymized` delivered to it. The customer goes in its
-- own column, never in `id`: a row whose id is hers would make this app her owner.
CREATE TABLE IF NOT EXISTS intruder_heard (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    customer_id TEXT NOT NULL
);
