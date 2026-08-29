CREATE TABLE IF NOT EXISTS w1076_messages (
    id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, wa_message_id TEXT NOT NULL, body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CONSTRAINT uq_w1076_messages_wa UNIQUE (hub_id, wa_message_id));
CREATE INDEX IF NOT EXISTS idx_w1076_messages_hub ON w1076_messages (hub_id);
