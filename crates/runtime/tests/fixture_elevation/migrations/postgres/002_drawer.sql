-- hub#362: a module table that NEVER heard of elevation. No `approved_by` column, and the command
-- that writes it never binds `:approved_by` — which is every table of every published module
-- today. It is here so the tests can prove the runtime records the approval anyway.
CREATE TABLE IF NOT EXISTS till_drawer_event (
    id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, reason TEXT NOT NULL,
    created_by TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_till_drawer_event_hub ON till_drawer_event (hub_id);
