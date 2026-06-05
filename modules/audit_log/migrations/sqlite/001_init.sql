-- Audit Log · esquema inicial (SQLite). Portado fielmente de old_modules/m_audit_log/models.py.
-- Modelos: AuditEvent (un registro de auditoría), AuditCategory (agrupación lógica con
-- severidad por defecto y política de retención) y AuditReport (informe de cumplimiento
-- agregado sobre un rango de fechas).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.
-- Las columnas JSON del legacy (before_state/after_state/changes/event_metadata/filters)
-- se almacenan como TEXT con JSON serializado (portable SQLite↔Postgres).

-- Evento de auditoría: una entrada del log. entity_* son libres (las entidades viven en
-- otros módulos). user_* están denormalizados para que el log sobreviva al borrado/renombrado
-- del usuario. occurred_at es el momento del evento (lo fija el servicio/runtime).
CREATE TABLE IF NOT EXISTS audit_log_event (
    id                   TEXT PRIMARY KEY,
    hub_id               TEXT NOT NULL,
    event_type           TEXT NOT NULL,                 -- entity_created|entity_updated|entity_deleted|login|logout|permission_change|data_export|config_change|api_call
    entity_type          TEXT NOT NULL DEFAULT '',
    entity_id            TEXT NOT NULL DEFAULT '',
    entity_repr          TEXT NOT NULL DEFAULT '',
    user_ref             TEXT NOT NULL DEFAULT '',       -- actor (denormalizado)
    user_email_snapshot  TEXT NOT NULL DEFAULT '',
    user_role_snapshot   TEXT NOT NULL DEFAULT '',
    ip_address           TEXT NOT NULL DEFAULT '',
    user_agent           TEXT NOT NULL DEFAULT '',
    before_state         TEXT,                           -- JSON serializado o NULL
    after_state          TEXT,                           -- JSON serializado o NULL
    changes              TEXT,                           -- JSON {campo:{before,after}} o NULL
    occurred_at          TEXT NOT NULL,                  -- ISO 8601
    severity             TEXT NOT NULL DEFAULT 'info',   -- info|warning|critical
    event_metadata       TEXT,                           -- JSON serializado o NULL
    is_deleted           INTEGER NOT NULL DEFAULT 0,
    deleted_at           TEXT,
    created_by           TEXT,
    updated_by           TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT
);
CREATE INDEX IF NOT EXISTS ix_al_hub_event_type   ON audit_log_event (hub_id, event_type);
CREATE INDEX IF NOT EXISTS ix_al_hub_entity       ON audit_log_event (hub_id, entity_type, entity_id);
CREATE INDEX IF NOT EXISTS ix_al_hub_user         ON audit_log_event (hub_id, user_ref);
CREATE INDEX IF NOT EXISTS ix_al_hub_occurred_at  ON audit_log_event (hub_id, occurred_at);
CREATE INDEX IF NOT EXISTS ix_al_hub_severity     ON audit_log_event (hub_id, severity);
CREATE INDEX IF NOT EXISTS idx_audit_log_event_hub ON audit_log_event (hub_id, is_deleted);

-- Categoría de auditoría: agrupación lógica con severidad por defecto y retención (días).
-- code es único por hub.
CREATE TABLE IF NOT EXISTS audit_log_category (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    code              TEXT NOT NULL,
    name              TEXT NOT NULL,
    severity_default  TEXT NOT NULL DEFAULT 'info',     -- info|warning|critical
    retention_days    INTEGER NOT NULL DEFAULT 365,
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_al_cat_hub_code        ON audit_log_category (hub_id, code);
CREATE INDEX        IF NOT EXISTS idx_audit_log_category_hub ON audit_log_category (hub_id, is_deleted);

-- Informe de cumplimiento agregado sobre un rango de fechas. report_number es único por hub
-- (formato AR-YYYYMMDD-NNNN). filters es JSON libre con los criterios usados al generarlo.
CREATE TABLE IF NOT EXISTS audit_log_report (
    id                 TEXT PRIMARY KEY,
    hub_id             TEXT NOT NULL,
    report_number      TEXT NOT NULL,
    generated_at       TEXT NOT NULL,                   -- ISO 8601
    generated_by_ref   TEXT NOT NULL DEFAULT '',
    period_start       TEXT NOT NULL,                   -- ISO 8601
    period_end         TEXT NOT NULL,                   -- ISO 8601
    filters            TEXT,                            -- JSON serializado o NULL
    total_events       INTEGER NOT NULL DEFAULT 0,
    status             TEXT NOT NULL DEFAULT 'generating', -- generating|ready|failed
    output_location    TEXT NOT NULL DEFAULT '',
    is_deleted         INTEGER NOT NULL DEFAULT 0,
    deleted_at         TEXT,
    created_by         TEXT,
    updated_by         TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_al_rep_hub_number     ON audit_log_report (hub_id, report_number);
CREATE INDEX        IF NOT EXISTS ix_al_rep_hub_status     ON audit_log_report (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_al_rep_hub_period     ON audit_log_report (hub_id, period_start, period_end);
CREATE INDEX        IF NOT EXISTS idx_audit_log_report_hub ON audit_log_report (hub_id, is_deleted);
