-- AI Reports · esquema inicial (SQLite). Portado fielmente de old_modules/m_ai_reports/models.py.
-- Modelos: AIReportTemplate (plantillas de prompt reutilizables), AIReportRequest (registro
-- auditado de peticiones LLM: prompt, respuesta, tokens, coste, ciclo de vida) y
-- AIReportCounter (secuencia atómica por hub+día para mintar AIR-YYYYMMDD-NNNN).
-- La llamada al LLM NO se hace aquí: el módulo solo persiste/audita la petición.
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Plantilla de prompt reutilizable que una petición puede referenciar.
-- code es único por hub y es el identificador estable. default_data_sources y
-- output_format guían cómo se construye el prompt y cómo se formatea la salida.
CREATE TABLE IF NOT EXISTS ai_reports_template (
    id                   TEXT PRIMARY KEY,
    hub_id               TEXT NOT NULL,
    code                 TEXT NOT NULL,
    name                 TEXT NOT NULL,
    description          TEXT NOT NULL DEFAULT '',
    prompt_template      TEXT NOT NULL,
    default_data_sources TEXT NOT NULL DEFAULT '[]',   -- JSON: lista de fuentes de datos esperadas
    output_format        TEXT NOT NULL DEFAULT 'markdown',  -- markdown|html|text
    is_active            INTEGER NOT NULL DEFAULT 1,
    is_deleted           INTEGER NOT NULL DEFAULT 0,
    deleted_at           TEXT,
    created_by           TEXT,
    updated_by           TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_ai_reports_template_hub_code   ON ai_reports_template (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_ai_reports_template_hub_active ON ai_reports_template (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS idx_ai_reports_template_hub       ON ai_reports_template (hub_id, is_deleted);

-- Petición de informe respaldada por LLM y su resultado.
-- request_number (AIR-YYYYMMDD-NNNN) es único por hub. template_id es un FK blando
-- (SET NULL al borrar la plantilla). El ciclo de vida es queued→running→completed/failed/cancelled.
CREATE TABLE IF NOT EXISTS ai_reports_request (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    request_number   TEXT NOT NULL,
    template_id      TEXT,
    user_query       TEXT NOT NULL,
    data_context     TEXT NOT NULL DEFAULT '{}',   -- JSON: contexto del prompt (tablas, filtros…)
    prompt_used      TEXT NOT NULL DEFAULT '',
    llm_response     TEXT NOT NULL DEFAULT '',
    tokens_used      INTEGER NOT NULL DEFAULT 0,
    cost_eur         NUMERIC NOT NULL DEFAULT 0,    -- Numeric(12,6)
    status           TEXT NOT NULL DEFAULT 'queued',  -- queued|running|completed|failed|cancelled
    requested_by_ref TEXT NOT NULL DEFAULT '',
    started_at       TEXT,
    completed_at     TEXT,
    error_message    TEXT NOT NULL DEFAULT '',
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT,
    FOREIGN KEY (template_id) REFERENCES ai_reports_template (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_ai_reports_request_hub_number      ON ai_reports_request (hub_id, request_number);
CREATE INDEX        IF NOT EXISTS ix_ai_reports_request_hub_status      ON ai_reports_request (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_ai_reports_request_hub_requestedby ON ai_reports_request (hub_id, requested_by_ref);
CREATE INDEX        IF NOT EXISTS ix_ai_reports_request_hub_created     ON ai_reports_request (hub_id, created_at);
CREATE INDEX        IF NOT EXISTS idx_ai_reports_request_hub            ON ai_reports_request (hub_id, is_deleted);

-- Contador atómico por hub+día usado para mintar AIR-YYYYMMDD-NNNN.
-- El incremento atómico (UPSERT ... RETURNING) es capacidad del runtime — ver WASM-TODO.
CREATE TABLE IF NOT EXISTS ai_reports_counter (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    day         TEXT NOT NULL,                 -- YYYYMMDD
    last_number INTEGER NOT NULL DEFAULT 0,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_ai_reports_counter_hub_day ON ai_reports_counter (hub_id, day);
CREATE INDEX        IF NOT EXISTS idx_ai_reports_counter_hub    ON ai_reports_counter (hub_id, is_deleted);
