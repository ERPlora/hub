-- Staff · esquema inicial (SQLite). Portado fielmente de old_modules/m_staff/models.py.
-- Modelos: StaffSettings (singleton por hub), StaffRole, StaffMember, StaffSchedule,
-- StaffWorkingHours, StaffTimeOff, StaffService. Es el módulo HR base (sin dependencias).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Configuración de staff por hub (singleton: único registro por hub_id).
CREATE TABLE IF NOT EXISTS staff_settings (
    id                     TEXT PRIMARY KEY,
    hub_id                 TEXT NOT NULL,
    default_work_start     TEXT NOT NULL DEFAULT '09:00:00',  -- HH:MM:SS
    default_work_end       TEXT NOT NULL DEFAULT '18:00:00',
    default_break_duration INTEGER NOT NULL DEFAULT 60,        -- minutos
    min_advance_booking    INTEGER NOT NULL DEFAULT 1,         -- horas
    max_daily_hours        INTEGER NOT NULL DEFAULT 12,
    overtime_threshold     INTEGER NOT NULL DEFAULT 40,        -- horas/semana
    show_staff_photos      INTEGER NOT NULL DEFAULT 1,
    show_staff_bio         INTEGER NOT NULL DEFAULT 1,
    allow_staff_selection  INTEGER NOT NULL DEFAULT 1,
    notify_new_appointment INTEGER NOT NULL DEFAULT 1,
    notify_cancellation    INTEGER NOT NULL DEFAULT 1,
    is_deleted             INTEGER NOT NULL DEFAULT 0,
    deleted_at             TEXT,
    created_by             TEXT,
    updated_by             TEXT,
    created_at             TEXT NOT NULL,
    updated_at             TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_staff_settings_hub ON staff_settings (hub_id);
CREATE INDEX        IF NOT EXISTS idx_staff_settings_hub ON staff_settings (hub_id, is_deleted);

-- Rol de staff (categorización: estilista, barbero, recepción...).
CREATE TABLE IF NOT EXISTS staff_role (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    color       TEXT NOT NULL DEFAULT '',          -- hex #RRGGBB
    "order"     INTEGER NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS ix_staff_role_hub_active ON staff_role (hub_id, is_active);
CREATE INDEX IF NOT EXISTS idx_staff_role_hub       ON staff_role (hub_id, is_deleted);

-- Miembro del staff (perfil). role_id es opcional (SET NULL al borrar rol).
-- status: active|inactive|on_leave|terminated.
CREATE TABLE IF NOT EXISTS staff_member (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    first_name       TEXT NOT NULL,
    last_name        TEXT NOT NULL,
    email            TEXT NOT NULL DEFAULT '',
    phone            TEXT NOT NULL DEFAULT '',
    photo            TEXT NOT NULL DEFAULT '',
    employee_id      TEXT NOT NULL DEFAULT '',
    role_id          TEXT,                          -- FK staff_role (SET NULL)
    user_id          TEXT,                          -- usuario vinculado (opcional)
    hire_date        TEXT,                          -- ISO YYYY-MM-DD
    termination_date TEXT,
    status           TEXT NOT NULL DEFAULT 'active',
    bio              TEXT NOT NULL DEFAULT '',
    specialties      TEXT NOT NULL DEFAULT '',      -- CSV de especialidades
    is_bookable      INTEGER NOT NULL DEFAULT 1,
    color            TEXT NOT NULL DEFAULT '',
    booking_buffer   INTEGER NOT NULL DEFAULT 0,    -- minutos entre citas
    hourly_rate      NUMERIC NOT NULL DEFAULT 0,
    commission_rate  NUMERIC NOT NULL DEFAULT 0,    -- % (0..100)
    "order"          INTEGER NOT NULL DEFAULT 0,
    notes            TEXT NOT NULL DEFAULT '',
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT,
    FOREIGN KEY (role_id) REFERENCES staff_role (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_staff_hub_status    ON staff_member (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_staff_hub_bookable  ON staff_member (hub_id, is_bookable);
CREATE INDEX IF NOT EXISTS idx_staff_member_hub   ON staff_member (hub_id, is_deleted);

-- Plantilla de horario semanal de un miembro.
CREATE TABLE IF NOT EXISTS staff_schedule (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    staff_id        TEXT NOT NULL,
    name            TEXT NOT NULL DEFAULT 'Default Schedule',
    is_default      INTEGER NOT NULL DEFAULT 1,
    effective_from  TEXT,                            -- ISO YYYY-MM-DD
    effective_until TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1,
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    FOREIGN KEY (staff_id) REFERENCES staff_member (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_staff_schedule_hub_staff ON staff_schedule (hub_id, staff_id);
CREATE INDEX IF NOT EXISTS idx_staff_schedule_hub      ON staff_schedule (hub_id, is_deleted);

-- Horas de trabajo por día de la semana dentro de un horario (day_of_week 0=Lunes..6=Domingo).
CREATE TABLE IF NOT EXISTS staff_working_hours (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    schedule_id TEXT NOT NULL,
    day_of_week INTEGER NOT NULL,                    -- 0..6
    start_time  TEXT NOT NULL,                       -- HH:MM:SS
    end_time    TEXT NOT NULL,
    break_start TEXT,
    break_end   TEXT,
    is_working  INTEGER NOT NULL DEFAULT 1,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT,
    FOREIGN KEY (schedule_id) REFERENCES staff_schedule (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_staff_working_hours_schedule_day ON staff_working_hours (schedule_id, day_of_week);
CREATE INDEX        IF NOT EXISTS idx_staff_working_hours_hub         ON staff_working_hours (hub_id, is_deleted);

-- Ausencias / vacaciones / bajas. leave_type: vacation|sick|personal|training|other.
-- status: pending|approved|rejected|cancelled.
CREATE TABLE IF NOT EXISTS staff_time_off (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    staff_id     TEXT NOT NULL,
    leave_type   TEXT NOT NULL DEFAULT 'vacation',
    start_date   TEXT NOT NULL,                      -- ISO YYYY-MM-DD
    end_date     TEXT NOT NULL,
    is_full_day  INTEGER NOT NULL DEFAULT 1,
    start_time   TEXT,                               -- HH:MM:SS si no es full day
    end_time     TEXT,
    status       TEXT NOT NULL DEFAULT 'pending',
    approved_by  TEXT,
    approved_at  TEXT,
    reason       TEXT NOT NULL DEFAULT '',
    notes        TEXT NOT NULL DEFAULT '',
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT,
    FOREIGN KEY (staff_id) REFERENCES staff_member (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_staff_time_off_hub_staff  ON staff_time_off (hub_id, staff_id);
CREATE INDEX IF NOT EXISTS ix_staff_time_off_hub_status ON staff_time_off (hub_id, status);
CREATE INDEX IF NOT EXISTS idx_staff_time_off_hub       ON staff_time_off (hub_id, is_deleted);

-- Servicios que un miembro puede prestar. service_id es opcional (integración con
-- el módulo services vía contrato; NO es FK a su tabla privada — solo se guarda el id).
CREATE TABLE IF NOT EXISTS staff_service (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    staff_id        TEXT NOT NULL,
    service_id      TEXT,                            -- referencia opaca a services.* (sin FK cross-módulo)
    service_name    TEXT NOT NULL,
    custom_duration INTEGER,                         -- minutos (override)
    custom_price    NUMERIC,                         -- override de precio
    is_primary      INTEGER NOT NULL DEFAULT 0,
    is_active       INTEGER NOT NULL DEFAULT 1,
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    FOREIGN KEY (staff_id) REFERENCES staff_member (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_staff_service_staff_service ON staff_service (staff_id, service_id);
CREATE INDEX        IF NOT EXISTS ix_staff_service_hub_staff     ON staff_service (hub_id, staff_id);
CREATE INDEX        IF NOT EXISTS idx_staff_service_hub          ON staff_service (hub_id, is_deleted);
