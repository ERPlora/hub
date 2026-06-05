-- KPIs · esquema inicial (SQLite). Portado fielmente de old_modules/m_kpis/models.py.
-- Modelos: KPI (definición de indicador con objetivo y umbrales), KPIValue (valor medido
-- por periodo) y KPIAlert (alerta cuando un valor cruza un umbral warning/critical).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Definición de un KPI: métrica seguida en el tiempo con objetivo, dirección de mejora
-- y umbrales opcionales. code es único por hub y es el identificador estable.
CREATE TABLE IF NOT EXISTS kpis_kpi (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    code                TEXT NOT NULL,
    name                TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    unit                TEXT NOT NULL DEFAULT 'count',            -- currency|percent|count|duration|ratio|score|other
    kpi_type            TEXT NOT NULL DEFAULT 'numerical',        -- numerical|percentage|count|ratio
    aggregation         TEXT NOT NULL DEFAULT 'last',             -- sum|avg|max|min|last
    category            TEXT NOT NULL DEFAULT '',
    target_value        NUMERIC,                                  -- objetivo (nullable)
    target_direction    TEXT NOT NULL DEFAULT 'higher_is_better', -- higher_is_better|lower_is_better
    critical_threshold  NUMERIC,                                  -- umbral crítico (nullable)
    warning_threshold   NUMERIC,                                  -- umbral aviso (nullable)
    is_active           INTEGER NOT NULL DEFAULT 1,
    owner_ref           TEXT,                                     -- referencia suelta a LocalUser (sin FK)
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_kpi_hub_code     ON kpis_kpi (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_kpi_hub_active   ON kpis_kpi (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS ix_kpi_hub_category ON kpis_kpi (hub_id, category);
CREATE INDEX        IF NOT EXISTS idx_kpis_kpi_hub    ON kpis_kpi (hub_id, is_deleted);

-- Valor medido de un KPI para un periodo cerrado [period_start, period_end].
-- target_at_time congela el objetivo en el momento del registro para histórico fiel.
CREATE TABLE IF NOT EXISTS kpis_value (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    kpi_id           TEXT NOT NULL,
    period_start     TEXT NOT NULL,                 -- ISO YYYY-MM-DD
    period_end       TEXT NOT NULL,                 -- ISO YYYY-MM-DD
    value            NUMERIC NOT NULL,
    target_at_time   NUMERIC,                       -- snapshot del objetivo (nullable)
    computed_at      TEXT,                          -- ISO datetime
    recorded_by_ref  TEXT,                          -- referencia suelta a LocalUser
    notes            TEXT NOT NULL DEFAULT '',
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT,
    FOREIGN KEY (kpi_id) REFERENCES kpis_kpi (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_kpi_value_hub_kpi_period ON kpis_value (hub_id, kpi_id, period_start);
CREATE INDEX IF NOT EXISTS ix_kpi_value_hub_period     ON kpis_value (hub_id, period_start);
CREATE INDEX IF NOT EXISTS idx_kpis_value_hub          ON kpis_value (hub_id, is_deleted);

-- Alerta generada cuando un valor cruza un umbral. Permanece hasta acknowledged.
CREATE TABLE IF NOT EXISTS kpis_alert (
    id                   TEXT PRIMARY KEY,
    hub_id               TEXT NOT NULL,
    kpi_id               TEXT NOT NULL,
    value_id             TEXT NOT NULL,
    alert_type           TEXT NOT NULL,             -- warning|critical|recovery
    triggered_at         TEXT NOT NULL,             -- ISO datetime
    message              TEXT NOT NULL DEFAULT '',
    acknowledged_at      TEXT,                      -- ISO datetime (NULL = sin reconocer)
    acknowledged_by_ref  TEXT,                      -- referencia suelta a LocalUser
    is_deleted           INTEGER NOT NULL DEFAULT 0,
    deleted_at           TEXT,
    created_by           TEXT,
    updated_by           TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT,
    FOREIGN KEY (kpi_id)   REFERENCES kpis_kpi (id)   ON DELETE CASCADE,
    FOREIGN KEY (value_id) REFERENCES kpis_value (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_kpi_alert_hub_kpi ON kpis_alert (hub_id, kpi_id);
CREATE INDEX IF NOT EXISTS ix_kpi_alert_hub_ack ON kpis_alert (hub_id, acknowledged_at);
CREATE INDEX IF NOT EXISTS idx_kpis_alert_hub   ON kpis_alert (hub_id, is_deleted);
