CREATE TABLE IF NOT EXISTS rec_order (
    hub_id TEXT NOT NULL,
    id TEXT NOT NULL,
    customer TEXT NOT NULL,
    notes TEXT,
    status TEXT NOT NULL,
    PRIMARY KEY (hub_id, id)
);
