-- Fixture: migración presente en el paquete pero NO listada en module.json (bug hubs Cloud).
CREATE TABLE IF NOT EXISTS migunion_empty_items (
    id     TEXT PRIMARY KEY,
    hub_id TEXT NOT NULL,
    name   TEXT NOT NULL
);
