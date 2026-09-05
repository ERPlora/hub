CREATE TABLE IF NOT EXISTS dberr_topic (
    id TEXT PRIMARY KEY, hub_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS dberr_note (
    id TEXT PRIMARY KEY, hub_id TEXT NOT NULL,
    topic_id TEXT NOT NULL REFERENCES dberr_topic (id),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    -- hub#1542: la columna NUMÉRICA sobre la que se declara un filtro `range`. Es el
    -- único tipo de columna que puede rechazar un extremo, y hace falta de verdad (no
    -- vale un doble): el rechazo lo decide el tipo que el SERVIDOR resuelve.
    weight INTEGER NOT NULL DEFAULT 0);
