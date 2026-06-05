-- Time Control · esquema inicial (SQLite). Portado fielmente de old_modules/m_time_control/models.py.
-- Control horario de empleados con geolocalización y geofencing.
-- Cumplimiento legal: Ley española de registro de jornada (RDL 8/2019).
-- Modelos: TimeControlSettings (singleton por hub), Workplace (centro de trabajo),
-- ClockRecord (fichaje individual) y DailySummary (resumen diario agregado por empleado).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Ajustes de control horario: una sola fila por hub (singleton).
-- geolocation_required y data_retention_months son sensibles legalmente (RDL 8/2019:
-- retención mínima 4 años = 48 meses). La validación >=48 vive en el handler WASM.
CREATE TABLE IF NOT EXISTS time_control_settings (
    id                      TEXT PRIMARY KEY,
    hub_id                  TEXT NOT NULL,
    geolocation_enabled     INTEGER NOT NULL DEFAULT 0,
    geolocation_required    INTEGER NOT NULL DEFAULT 0,
    geofence_radius_meters  INTEGER NOT NULL DEFAULT 100,
    auto_clock_out_enabled  INTEGER NOT NULL DEFAULT 0,
    auto_clock_out_hours    INTEGER NOT NULL DEFAULT 10,
    allow_manual_records    INTEGER NOT NULL DEFAULT 1,
    require_notes_manual    INTEGER NOT NULL DEFAULT 0,
    data_retention_months   INTEGER NOT NULL DEFAULT 48,
    is_deleted              INTEGER NOT NULL DEFAULT 0,
    deleted_at              TEXT,
    created_by              TEXT,
    updated_by              TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT
);
-- Singleton por hub: solo una fila activa por hub_id.
CREATE UNIQUE INDEX IF NOT EXISTS uq_tc_settings_hub      ON time_control_settings (hub_id);
CREATE INDEX        IF NOT EXISTS idx_time_control_settings_hub ON time_control_settings (hub_id, is_deleted);

-- Centro de trabajo físico para geofencing. latitude/longitude opcionales;
-- radius_meters es el radio de la geocerca. is_default marca el centro por defecto.
CREATE TABLE IF NOT EXISTS time_control_workplace (
    id             TEXT PRIMARY KEY,
    hub_id         TEXT NOT NULL,
    name           TEXT NOT NULL,
    address        TEXT NOT NULL DEFAULT '',
    latitude       NUMERIC,                       -- grados decimales o NULL
    longitude      NUMERIC,                       -- grados decimales o NULL
    radius_meters  INTEGER NOT NULL DEFAULT 100,
    is_active      INTEGER NOT NULL DEFAULT 1,
    is_default     INTEGER NOT NULL DEFAULT 0,
    is_deleted     INTEGER NOT NULL DEFAULT 0,
    deleted_at     TEXT,
    created_by     TEXT,
    updated_by     TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT
);
CREATE INDEX IF NOT EXISTS ix_tc_workplace_hub_active ON time_control_workplace (hub_id, is_active);
CREATE INDEX IF NOT EXISTS idx_time_control_workplace_hub ON time_control_workplace (hub_id, is_deleted);

-- Fichaje individual: evento de entrada/salida/inicio-fin de pausa de un empleado.
-- record_type: clock_in|clock_out|break_start|break_end. method: pin|auto|manual|api.
-- employee_id referencia al empleado del módulo staff (NO FK física: cross-módulo
-- por contrato). Geolocalización y geofence (is_within_geofence) opcionales.
CREATE TABLE IF NOT EXISTS time_control_clock_record (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    employee_id         TEXT NOT NULL,
    employee_name       TEXT NOT NULL DEFAULT '',
    timestamp           TEXT NOT NULL,            -- ISO 8601 con zona horaria
    record_type         TEXT NOT NULL,            -- clock_in|clock_out|break_start|break_end
    method              TEXT NOT NULL DEFAULT 'pin', -- pin|auto|manual|api
    latitude            NUMERIC,
    longitude           NUMERIC,
    address             TEXT,
    workplace_id        TEXT,                      -- ref a time_control_workplace.id o NULL
    is_within_geofence  INTEGER,                   -- 1/0/NULL (NULL = no evaluado)
    ip_address          TEXT,
    user_agent          TEXT,
    notes               TEXT NOT NULL DEFAULT '',
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT,
    FOREIGN KEY (workplace_id) REFERENCES time_control_workplace (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_tc_hub_employee_timestamp ON time_control_clock_record (hub_id, employee_id, timestamp);
CREATE INDEX IF NOT EXISTS ix_tc_hub_timestamp          ON time_control_clock_record (hub_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_time_control_clock_record_hub ON time_control_clock_record (hub_id, is_deleted);

-- Resumen diario agregado por empleado y fecha. total_work_minutes / total_break_minutes
-- los calcula el handler WASM emparejando los fichajes cronológicamente. Único por
-- (hub, employee, date).
CREATE TABLE IF NOT EXISTS time_control_daily_summary (
    id                   TEXT PRIMARY KEY,
    hub_id               TEXT NOT NULL,
    employee_id          TEXT NOT NULL,
    employee_name        TEXT NOT NULL DEFAULT '',
    date                 TEXT NOT NULL,            -- ISO YYYY-MM-DD
    first_clock_in       TEXT,                     -- ISO 8601 o NULL
    last_clock_out       TEXT,                     -- ISO 8601 o NULL
    total_work_minutes   INTEGER NOT NULL DEFAULT 0,
    total_break_minutes  INTEGER NOT NULL DEFAULT 0,
    clock_count          INTEGER NOT NULL DEFAULT 0,
    is_complete          INTEGER NOT NULL DEFAULT 0,
    is_deleted           INTEGER NOT NULL DEFAULT 0,
    deleted_at           TEXT,
    created_by           TEXT,
    updated_by           TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tc_daily_summary           ON time_control_daily_summary (hub_id, employee_id, date);
CREATE INDEX        IF NOT EXISTS ix_tc_summary_hub_employee_date ON time_control_daily_summary (hub_id, employee_id, date);
CREATE INDEX        IF NOT EXISTS idx_time_control_daily_summary_hub ON time_control_daily_summary (hub_id, is_deleted);
