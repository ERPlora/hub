-- Leave · esquema inicial (SQLite). Portado fielmente de old_modules/m_leave/models.py.
-- Modelos: LeaveSettings (singleton por hub), LeaveType (catálogo), LeaveRequest
-- (solicitud con workflow pending/approved/rejected/cancelled) y LeaveBalance
-- (saldo por empleado/tipo/año). Contrato de fila estándar de hub-next (§2.5):
-- hub_id + soft-delete + auditoría en todas las tablas.

-- Ajustes de ausencias: singleton por hub (un único registro por hub_id).
CREATE TABLE IF NOT EXISTS leave_settings (
    id                   TEXT PRIMARY KEY,
    hub_id               TEXT NOT NULL,
    default_days_per_year INTEGER NOT NULL DEFAULT 22,
    require_approval     INTEGER NOT NULL DEFAULT 1,
    min_advance_days     INTEGER NOT NULL DEFAULT 1,
    allow_half_days      INTEGER NOT NULL DEFAULT 1,
    max_consecutive_days INTEGER NOT NULL DEFAULT 30,
    is_deleted           INTEGER NOT NULL DEFAULT 0,
    deleted_at           TEXT,
    created_by           TEXT,
    updated_by           TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT
);
-- Un solo registro de ajustes por hub.
CREATE UNIQUE INDEX IF NOT EXISTS uq_leave_settings_hub ON leave_settings (hub_id);
CREATE INDEX        IF NOT EXISTS idx_leave_settings_hub ON leave_settings (hub_id, is_deleted);

-- Tipo de ausencia (vacaciones, baja, asuntos propios...). days_per_year = entitlement
-- base; color e is_paid para presentación/cálculo. is_active permite ocultarlo sin borrar.
CREATE TABLE IF NOT EXISTS leave_type (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    name          TEXT NOT NULL,
    days_per_year INTEGER NOT NULL DEFAULT 0,
    is_paid       INTEGER NOT NULL DEFAULT 1,
    color         TEXT NOT NULL DEFAULT '#3b82f6',
    is_active     INTEGER NOT NULL DEFAULT 1,
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT
);
CREATE INDEX IF NOT EXISTS ix_leave_type_hub_active ON leave_type (hub_id, is_active);
CREATE INDEX IF NOT EXISTS idx_leave_type_hub       ON leave_type (hub_id, is_deleted);

-- Solicitud de ausencia. employee_id/employee_name son una copia del empleado del
-- módulo staff (cross-módulo por valor; NO hay FK a tablas de staff). status sigue el
-- workflow pending|approved|rejected|cancelled. days_count se calcula (días hábiles o 0.5).
CREATE TABLE IF NOT EXISTS leave_request (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    employee_id      TEXT NOT NULL,
    employee_name    TEXT NOT NULL,
    leave_type_id    TEXT NOT NULL,
    start_date       TEXT NOT NULL,           -- ISO YYYY-MM-DD
    end_date         TEXT NOT NULL,           -- ISO YYYY-MM-DD
    days_count       NUMERIC NOT NULL DEFAULT 1.0,
    is_half_day      INTEGER NOT NULL DEFAULT 0,
    half_day_period  TEXT,                     -- morning|afternoon o NULL
    status           TEXT NOT NULL DEFAULT 'pending',
    reason           TEXT NOT NULL DEFAULT '',
    approved_by      TEXT,                     -- user_id que aprobó
    approved_at      TEXT,                     -- ISO timestamp
    rejection_reason TEXT,
    notes            TEXT NOT NULL DEFAULT '',
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT,
    FOREIGN KEY (leave_type_id) REFERENCES leave_type (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_leave_request_hub_employee ON leave_request (hub_id, employee_id);
CREATE INDEX IF NOT EXISTS ix_leave_request_hub_status   ON leave_request (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_leave_request_hub_dates    ON leave_request (hub_id, start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_leave_request_hub         ON leave_request (hub_id, is_deleted);

-- Saldo de ausencias por empleado/tipo/año. entitled+carried-used-pending = remaining.
-- used_days/pending_days son rollups del workflow (no se editan directamente desde set).
CREATE TABLE IF NOT EXISTS leave_balance (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    employee_id   TEXT NOT NULL,
    employee_name TEXT NOT NULL,
    leave_type_id TEXT NOT NULL,
    year          INTEGER NOT NULL,
    entitled_days NUMERIC NOT NULL DEFAULT 0.0,
    used_days     NUMERIC NOT NULL DEFAULT 0.0,
    pending_days  NUMERIC NOT NULL DEFAULT 0.0,
    carried_over  NUMERIC NOT NULL DEFAULT 0.0,
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT,
    FOREIGN KEY (leave_type_id) REFERENCES leave_type (id) ON DELETE CASCADE
);
-- Un saldo único por (hub, empleado, tipo, año).
CREATE UNIQUE INDEX IF NOT EXISTS uq_leave_balance_employee_type_year
    ON leave_balance (hub_id, employee_id, leave_type_id, year);
CREATE INDEX IF NOT EXISTS ix_leave_balance_hub_employee_year ON leave_balance (hub_id, employee_id, year);
CREATE INDEX IF NOT EXISTS idx_leave_balance_hub              ON leave_balance (hub_id, is_deleted);
