CREATE TABLE IF NOT EXISTS nid_item (
    hub_id TEXT NOT NULL,
    id TEXT NOT NULL,
    name TEXT,
    PRIMARY KEY (hub_id, id)
);
