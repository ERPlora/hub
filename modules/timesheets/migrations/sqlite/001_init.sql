-- Timesheets · esquema inicial (SQLite). Portado fielmente de old_modules/m_timesheets/models.py.
-- Modelos: TimesheetsSettings (singleton por hub), HourlyRate (tarifa horaria),
-- TimeEntry (registro de tiempo de un empleado) y TimesheetApproval (lote de aprobación
-- por periodo y empleado). Contrato de fila estándar de hub-next (§2.5): hub_id +
-- soft-delete + auditoría.

-- Configuración de timesheets del hub (singleton: una fila por hub).
CREATE TABLE IF NOT EXISTS timesheets_settings (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    default_billable INTEGER NOT NULL DEFAULT 1,
    require_approval INTEGER NOT NULL DEFAULT 1,
    approval_period  TEXT NOT NULL DEFAULT 'weekly',  -- weekly|biweekly|monthly
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_timesheets_settings_hub ON timesheets_settings (hub_id);
CREATE INDEX        IF NOT EXISTS idx_timesheets_settings_hub ON timesheets_settings (hub_id, is_deleted);

-- Tarifa horaria de facturación. employee_id opcional (tarifa por empleado o global).
CREATE TABLE IF NOT EXISTS timesheets_hourly_rate (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    name        TEXT NOT NULL,
    rate        NUMERIC NOT NULL DEFAULT 0,
    employee_id TEXT,                          -- referencia a staff (módulo externo) o NULL
    is_default  INTEGER NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS ix_timesheets_rate_hub_name ON timesheets_hourly_rate (hub_id, name);
CREATE INDEX IF NOT EXISTS ix_timesheets_rate_hub_active ON timesheets_hourly_rate (hub_id, is_active);
CREATE INDEX IF NOT EXISTS idx_timesheets_hourly_rate_hub ON timesheets_hourly_rate (hub_id, is_deleted);

-- Registro de tiempo individual de un empleado.
-- duration_minutes es la fuente de verdad; rate_amount captura la tarifa en el momento.
-- status: draft|submitted|approved|rejected. La transición de aprobación va a runtime.
CREATE TABLE IF NOT EXISTS timesheets_time_entry (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    employee_id     TEXT NOT NULL,             -- referencia a staff (módulo externo)
    employee_name   TEXT NOT NULL DEFAULT '',
    date            TEXT NOT NULL,             -- ISO YYYY-MM-DD
    start_time      TEXT,                      -- ISO HH:MM:SS o NULL
    end_time        TEXT,                      -- ISO HH:MM:SS o NULL
    duration_minutes INTEGER NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'draft',
    billable        INTEGER NOT NULL DEFAULT 1,
    project_name    TEXT NOT NULL DEFAULT '',
    client_name     TEXT NOT NULL DEFAULT '',
    hourly_rate_id  TEXT,                      -- FK a timesheets_hourly_rate o NULL
    rate_amount     NUMERIC,                   -- tarifa capturada en el alta o NULL
    approved_by     TEXT,
    approved_at     TEXT,
    rejection_notes TEXT NOT NULL DEFAULT '',
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    FOREIGN KEY (hourly_rate_id) REFERENCES timesheets_hourly_rate (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_timesheets_entry_hub_employee ON timesheets_time_entry (hub_id, employee_id);
CREATE INDEX IF NOT EXISTS ix_timesheets_entry_hub_date     ON timesheets_time_entry (hub_id, date);
CREATE INDEX IF NOT EXISTS ix_timesheets_entry_hub_status   ON timesheets_time_entry (hub_id, status);
CREATE INDEX IF NOT EXISTS idx_timesheets_time_entry_hub    ON timesheets_time_entry (hub_id, is_deleted);

-- Lote de aprobación de un periodo de tiempo para un empleado.
-- status: pending|approved|rejected. total_hours/billable_hours son agregados del periodo.
CREATE TABLE IF NOT EXISTS timesheets_approval (
    id             TEXT PRIMARY KEY,
    hub_id         TEXT NOT NULL,
    employee_id    TEXT NOT NULL,              -- referencia a staff (módulo externo)
    employee_name  TEXT NOT NULL DEFAULT '',
    period_start   TEXT NOT NULL,              -- ISO YYYY-MM-DD
    period_end     TEXT NOT NULL,              -- ISO YYYY-MM-DD
    status         TEXT NOT NULL DEFAULT 'pending',
    approved_by    TEXT,
    approved_at    TEXT,
    total_hours    NUMERIC NOT NULL DEFAULT 0,
    billable_hours NUMERIC NOT NULL DEFAULT 0,
    notes          TEXT NOT NULL DEFAULT '',
    is_deleted     INTEGER NOT NULL DEFAULT 0,
    deleted_at     TEXT,
    created_by     TEXT,
    updated_by     TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT
);
CREATE INDEX IF NOT EXISTS ix_timesheets_approval_hub_employee ON timesheets_approval (hub_id, employee_id);
CREATE INDEX IF NOT EXISTS ix_timesheets_approval_hub_status   ON timesheets_approval (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_timesheets_approval_hub_period   ON timesheets_approval (hub_id, period_start);
CREATE INDEX IF NOT EXISTS idx_timesheets_approval_hub         ON timesheets_approval (hub_id, is_deleted);
