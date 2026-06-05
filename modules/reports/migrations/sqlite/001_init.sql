-- Reports · esquema inicial (SQLite). Portado fielmente de old_modules/m_reports/models.py.
-- Modelos: Report (definición reutilizable: data source + columnas + filtros + groupings + sorts),
-- ReportRun (historial de ejecución con metadatos de salida) y ReportSubscription (entrega
-- recurrente por usuario). Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.
-- Los campos JSON (filters/columns/groupings/sorts/schedule/filters_applied) se almacenan como TEXT (JSON).

-- Definición de informe: fuente de datos + columnas + filtros + agrupaciones + ordenaciones.
-- code es único por hub y es el identificador estable referenciado por runs/subscriptions.
CREATE TABLE IF NOT EXISTS reports_report (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    code         TEXT NOT NULL,
    name         TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    report_type  TEXT NOT NULL DEFAULT 'table',   -- table|pivot|timeseries|comparison|funnel
    data_source  TEXT NOT NULL,
    filters      TEXT,                             -- JSON libre o NULL
    columns      TEXT,                             -- JSON (lista) o NULL
    groupings    TEXT,                             -- JSON (lista) o NULL
    sorts        TEXT,                             -- JSON (lista) o NULL
    is_public    INTEGER NOT NULL DEFAULT 0,
    schedule     TEXT,                             -- JSON o NULL
    owner_ref    TEXT,                             -- uuid de LocalUser (referencia suelta, sin FK)
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_reports_hub_code        ON reports_report (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_reports_hub_type        ON reports_report (hub_id, report_type);
CREATE INDEX        IF NOT EXISTS ix_reports_hub_data_source ON reports_report (hub_id, data_source);
CREATE INDEX        IF NOT EXISTS ix_reports_hub_owner       ON reports_report (hub_id, owner_ref);
CREATE INDEX        IF NOT EXISTS idx_reports_report_hub     ON reports_report (hub_id, is_deleted);

-- Ejecución única de un informe: historial + metadatos de salida.
-- run_number ('RPT-YYYYMMDD-NNNN') es único por hub. Los datos viven en S3/disco;
-- aquí guardamos solo el localizador (output_location) y el conteo (total_rows).
CREATE TABLE IF NOT EXISTS reports_run (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    report_id       TEXT NOT NULL,
    run_number      TEXT NOT NULL,
    filters_applied TEXT,                          -- JSON (filtros base + overrides fusionados) o NULL
    started_at      TEXT,                          -- ISO timestamp o NULL
    completed_at    TEXT,                          -- ISO timestamp o NULL
    status          TEXT NOT NULL DEFAULT 'running', -- running|completed|failed
    total_rows      INTEGER NOT NULL DEFAULT 0,
    output_format   TEXT NOT NULL DEFAULT 'json',  -- json|csv|xlsx|pdf
    output_location TEXT NOT NULL DEFAULT '',
    run_by_ref      TEXT,                          -- uuid de LocalUser (referencia suelta, sin FK)
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    FOREIGN KEY (report_id) REFERENCES reports_report (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_reports_hub_run_number ON reports_run (hub_id, run_number);
CREATE INDEX        IF NOT EXISTS ix_reports_run_hub_report ON reports_run (hub_id, report_id);
CREATE INDEX        IF NOT EXISTS ix_reports_run_hub_status ON reports_run (hub_id, status);
CREATE INDEX        IF NOT EXISTS idx_reports_run_hub       ON reports_run (hub_id, is_deleted);

-- Suscripción de entrega recurrente de un informe por usuario.
CREATE TABLE IF NOT EXISTS reports_subscription (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    report_id       TEXT NOT NULL,
    subscriber_ref  TEXT,                          -- uuid de LocalUser (referencia suelta, sin FK)
    frequency       TEXT NOT NULL DEFAULT 'weekly', -- daily|weekly|monthly
    delivery_method TEXT NOT NULL DEFAULT 'email', -- email|webhook
    is_active       INTEGER NOT NULL DEFAULT 1,
    last_sent_at    TEXT,                          -- ISO timestamp o NULL
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    FOREIGN KEY (report_id) REFERENCES reports_report (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_reports_sub_hub_report     ON reports_subscription (hub_id, report_id);
CREATE INDEX IF NOT EXISTS ix_reports_sub_hub_subscriber ON reports_subscription (hub_id, subscriber_ref);
CREATE INDEX IF NOT EXISTS idx_reports_subscription_hub  ON reports_subscription (hub_id, is_deleted);
