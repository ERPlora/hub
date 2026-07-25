-- Fixture: 001 existe en el paquete pero el manifest solo lista 002 (caso `invoice` real).
CREATE TABLE IF NOT EXISTS migunion_partial_items (
    id     TEXT PRIMARY KEY,
    hub_id TEXT NOT NULL,
    name   TEXT NOT NULL
);
