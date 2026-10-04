CREATE TABLE IF NOT EXISTS set_aside_request (
    hub_id TEXT NOT NULL,
    id TEXT NOT NULL,
    customer_id TEXT,
    data TEXT,
    deleted_at TEXT,
    PRIMARY KEY (hub_id, id)
);
