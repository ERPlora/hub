-- Attendance · esquema inicial (SQLite). Portado fielmente de modules/m_attendance/models.py.
-- Modelos: AttendanceSettings (configuración singleton por hub) y AttendanceRecord
-- (un fichaje de entrada/salida por empleado).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Configuración de fichajes por hub (singleton: una fila por hub_id).
-- Controla foto obligatoria, entrada manual, umbral de retraso/salida anticipada
-- y horas tras las que se auto-cierra un fichaje abierto.
CREATE TABLE IF NOT EXISTS attendance_settings (
    id                      TEXT PRIMARY KEY,
    hub_id                  TEXT NOT NULL,
    require_photo           INTEGER NOT NULL DEFAULT 0,
    allow_manual_entry      INTEGER NOT NULL DEFAULT 1,
    late_threshold_minutes  INTEGER NOT NULL DEFAULT 15,
    early_departure_minutes INTEGER NOT NULL DEFAULT 15,
    auto_clock_out_hours    INTEGER NOT NULL DEFAULT 12,
    is_deleted              INTEGER NOT NULL DEFAULT 0,
    deleted_at              TEXT,
    created_by              TEXT,
    updated_by              TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT
);
-- Singleton: una única fila de settings por hub.
CREATE UNIQUE INDEX IF NOT EXISTS uq_attendance_settings_hub ON attendance_settings (hub_id);
CREATE INDEX        IF NOT EXISTS idx_attendance_settings_hub ON attendance_settings (hub_id, is_deleted);

-- Fichaje individual de un empleado. clock_out NULL = fichaje abierto (aún dentro).
-- total_hours se recalcula al cerrar (clock_out - clock_in - break) en el handler WASM.
-- status: present | late | absent | half_day | remote.
CREATE TABLE IF NOT EXISTS attendance_record (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    employee_id   TEXT NOT NULL,
    employee_name TEXT NOT NULL,
    clock_in      TEXT NOT NULL,                 -- ISO-8601 datetime
    clock_out     TEXT,                          -- ISO-8601 datetime o NULL (abierto)
    break_minutes INTEGER NOT NULL DEFAULT 0,
    total_hours   NUMERIC NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'present',
    notes         TEXT NOT NULL DEFAULT '',
    location      TEXT,
    device        TEXT,
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT
);
CREATE INDEX IF NOT EXISTS ix_attendance_hub_employee ON attendance_record (hub_id, employee_id);
CREATE INDEX IF NOT EXISTS ix_attendance_hub_clock_in ON attendance_record (hub_id, clock_in);
CREATE INDEX IF NOT EXISTS ix_attendance_hub_status   ON attendance_record (hub_id, status);
CREATE INDEX IF NOT EXISTS idx_attendance_record_hub  ON attendance_record (hub_id, is_deleted);
