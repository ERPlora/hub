-- Notas · esquema inicial (SQLite). Contrato de fila estándar de hub-next (§2.5).
CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, title TEXT NOT NULL, body TEXT,
    is_deleted INTEGER NOT NULL DEFAULT 0, created_by TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_notes_hub ON notes (hub_id, is_deleted);
