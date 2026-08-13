CREATE TABLE IF NOT EXISTS scoped_ok_item (
    hub_id TEXT NOT NULL,
    id TEXT NOT NULL,
    n INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (hub_id, id)
);
CREATE INDEX IF NOT EXISTS scoped_ok_item_n ON scoped_ok_item (n);
