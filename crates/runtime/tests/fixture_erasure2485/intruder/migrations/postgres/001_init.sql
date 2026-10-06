-- A test app for hub#2485: it owns notes, and nothing else.
CREATE TABLE IF NOT EXISTS intruder_note (
    id     TEXT PRIMARY KEY,
    hub_id TEXT NOT NULL,
    body   TEXT NOT NULL DEFAULT ''
);
