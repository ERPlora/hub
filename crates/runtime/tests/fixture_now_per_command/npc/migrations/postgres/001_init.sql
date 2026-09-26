CREATE TABLE IF NOT EXISTS npc_item (
    hub_id TEXT NOT NULL,
    id TEXT NOT NULL,
    updated_at TEXT,
    PRIMARY KEY (hub_id, id)
);
CREATE TABLE IF NOT EXISTS npc_trail (
    hub_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    stamped_at TEXT NOT NULL,
    handler_now TEXT,
    payload_now TEXT
);
