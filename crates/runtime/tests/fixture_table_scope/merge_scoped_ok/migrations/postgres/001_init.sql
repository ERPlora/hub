CREATE TABLE IF NOT EXISTS merge_scoped_ok_item (
    hub_id TEXT NOT NULL,
    id TEXT NOT NULL,
    n INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (hub_id, id)
);
