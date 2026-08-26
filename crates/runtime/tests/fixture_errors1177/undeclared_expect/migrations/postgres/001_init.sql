CREATE TABLE IF NOT EXISTS e1177_item (
    hub_id TEXT NOT NULL,
    id TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'open',
    PRIMARY KEY (hub_id, id)
);
