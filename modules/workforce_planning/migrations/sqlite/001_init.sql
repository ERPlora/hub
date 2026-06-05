-- Workforce Planning · esquema inicial (SQLite). Portado de old_modules/m_workforce_planning/models.py.
-- Planificación de plantilla multi-sede: ajustes por hub, sedes, plantillas de turno,
-- asignaciones concretas de turno, calendario laboral (festivos), requisitos de cobertura
-- y conflictos detectados (doble reserva, horas extra, descanso insuficiente, hueco de cobertura).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.
-- Las FK entre tablas del PROPIO módulo son válidas (cada módulo OWNea sus tablas);
-- employee_id / manager_employee_id apuntan al módulo staff por valor (NO hay FK cross-módulo).

-- Ajustes de planificación (singleton por hub). uq por hub_id.
CREATE TABLE IF NOT EXISTS workforce_planning_settings (
    id                            TEXT PRIMARY KEY,
    hub_id                        TEXT NOT NULL,
    default_shift_duration_hours  INTEGER NOT NULL DEFAULT 8,
    max_weekly_hours              INTEGER NOT NULL DEFAULT 40,
    min_rest_hours_between_shifts INTEGER NOT NULL DEFAULT 11,
    overtime_weekly_threshold     INTEGER NOT NULL DEFAULT 40,
    require_manager_approval      INTEGER NOT NULL DEFAULT 1,
    auto_detect_conflicts         INTEGER NOT NULL DEFAULT 1,
    is_deleted                    INTEGER NOT NULL DEFAULT 0,
    deleted_at                    TEXT,
    created_by                    TEXT,
    updated_by                    TEXT,
    created_at                    TEXT NOT NULL,
    updated_at                    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_wp_settings_hub        ON workforce_planning_settings (hub_id);
CREATE INDEX        IF NOT EXISTS idx_wp_settings_hub       ON workforce_planning_settings (hub_id, is_deleted);

-- Sede: sucursal física donde trabajan los empleados.
-- manager_employee_id referencia un empleado del módulo staff (por valor, sin FK cross-módulo).
CREATE TABLE IF NOT EXISTS workforce_planning_location (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    name                TEXT NOT NULL,
    address             TEXT,
    phone               TEXT,
    email               TEXT,
    manager_employee_id TEXT,
    timezone            TEXT NOT NULL DEFAULT 'Europe/Madrid',
    is_active           INTEGER NOT NULL DEFAULT 1,
    color               TEXT NOT NULL DEFAULT '#3b82f6',
    sort_order          INTEGER NOT NULL DEFAULT 0,
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT
);
CREATE INDEX IF NOT EXISTS ix_wp_location_hub_active ON workforce_planning_location (hub_id, is_active);
CREATE INDEX IF NOT EXISTS idx_wp_location_hub       ON workforce_planning_location (hub_id, is_deleted);

-- Plantilla de turno reutilizable (p.ej. "Turno de mañana 7:00-15:00").
-- required_skills se guarda como JSON array de nombres de skill (portable SQLite + Postgres).
CREATE TABLE IF NOT EXISTS workforce_planning_shift_template (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    name             TEXT NOT NULL,
    location_id      TEXT,
    start_time       TEXT NOT NULL,                -- HH:MM
    end_time         TEXT NOT NULL,                -- HH:MM
    break_minutes    INTEGER NOT NULL DEFAULT 0,
    color            TEXT NOT NULL DEFAULT '#3b82f6',
    is_active        INTEGER NOT NULL DEFAULT 1,
    min_staff        INTEGER NOT NULL DEFAULT 1,
    max_staff        INTEGER NOT NULL DEFAULT 0,
    role_required    TEXT,
    required_skills  TEXT NOT NULL DEFAULT '[]',   -- JSON array de nombres de skill
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT,
    FOREIGN KEY (location_id) REFERENCES workforce_planning_location (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_wp_shift_tpl_hub_location ON workforce_planning_shift_template (hub_id, location_id);
CREATE INDEX IF NOT EXISTS ix_wp_shift_tpl_hub_active   ON workforce_planning_shift_template (hub_id, is_active);
CREATE INDEX IF NOT EXISTS idx_wp_shift_template_hub    ON workforce_planning_shift_template (hub_id, is_deleted);

-- Asignación concreta de un empleado a un turno, en una sede y una fecha.
-- status: scheduled|confirmed|completed|cancelled|no_show.
CREATE TABLE IF NOT EXISTS workforce_planning_shift_assignment (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    employee_id       TEXT NOT NULL,               -- staff.employee (por valor)
    employee_name     TEXT NOT NULL,
    location_id       TEXT NOT NULL,
    shift_template_id TEXT,
    date              TEXT NOT NULL,               -- ISO YYYY-MM-DD
    start_time        TEXT NOT NULL,               -- HH:MM
    end_time          TEXT NOT NULL,               -- HH:MM
    break_minutes     INTEGER NOT NULL DEFAULT 0,
    status            TEXT NOT NULL DEFAULT 'scheduled',
    notes             TEXT NOT NULL DEFAULT '',
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    FOREIGN KEY (location_id)       REFERENCES workforce_planning_location (id)       ON DELETE CASCADE,
    FOREIGN KEY (shift_template_id) REFERENCES workforce_planning_shift_template (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_wp_assignment_hub_date_employee ON workforce_planning_shift_assignment (hub_id, date, employee_id);
CREATE INDEX IF NOT EXISTS ix_wp_assignment_hub_date_location ON workforce_planning_shift_assignment (hub_id, date, location_id);
CREATE INDEX IF NOT EXISTS idx_wp_shift_assignment_hub        ON workforce_planning_shift_assignment (hub_id, is_deleted);

-- Calendario laboral: festivos, días especiales y sus reglas de pago.
-- calendar_type: public_holiday|regional_holiday|company_holiday|special_day.
-- uq por (hub, date, calendar_type, region).
CREATE TABLE IF NOT EXISTS workforce_planning_labor_calendar (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    date             TEXT NOT NULL,                -- ISO YYYY-MM-DD
    name             TEXT NOT NULL,
    calendar_type    TEXT NOT NULL DEFAULT 'public_holiday',
    region           TEXT,                         -- p.ej. ES-MD
    is_working_day   INTEGER NOT NULL DEFAULT 0,
    pay_multiplier   NUMERIC NOT NULL DEFAULT 2.00,
    recurring_yearly INTEGER NOT NULL DEFAULT 0,
    notes            TEXT NOT NULL DEFAULT '',
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_wp_labor_calendar ON workforce_planning_labor_calendar (hub_id, date, calendar_type, region);
CREATE INDEX        IF NOT EXISTS ix_wp_labor_cal_hub_date ON workforce_planning_labor_calendar (hub_id, date);
CREATE INDEX        IF NOT EXISTS idx_wp_labor_calendar_hub ON workforce_planning_labor_calendar (hub_id, is_deleted);

-- Requisito de cobertura: mínimo de personal por sede/turno/día de la semana.
-- day_of_week: 0=Lunes … 6=Domingo, o NULL = cualquier día.
CREATE TABLE IF NOT EXISTS workforce_planning_coverage_requirement (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    location_id       TEXT NOT NULL,
    day_of_week       INTEGER,
    shift_template_id TEXT,
    min_employees     INTEGER NOT NULL DEFAULT 1,
    role_required     TEXT,
    is_active         INTEGER NOT NULL DEFAULT 1,
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    FOREIGN KEY (location_id)       REFERENCES workforce_planning_location (id)       ON DELETE CASCADE,
    FOREIGN KEY (shift_template_id) REFERENCES workforce_planning_shift_template (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_wp_coverage_hub_location ON workforce_planning_coverage_requirement (hub_id, location_id);
CREATE INDEX IF NOT EXISTS idx_wp_coverage_req_hub     ON workforce_planning_coverage_requirement (hub_id, is_deleted);

-- Conflicto de planificación detectado.
-- conflict_type: double_booking|overtime|insufficient_rest|coverage_gap.
CREATE TABLE IF NOT EXISTS workforce_planning_conflict (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    employee_id         TEXT NOT NULL,            -- staff.employee (por valor)
    employee_name       TEXT NOT NULL,
    conflict_type       TEXT NOT NULL,
    date                TEXT NOT NULL,            -- ISO YYYY-MM-DD
    details             TEXT NOT NULL,
    shift_assignment_id TEXT,
    is_resolved         INTEGER NOT NULL DEFAULT 0,
    resolved_by         TEXT,
    resolved_at         TEXT,
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT,
    FOREIGN KEY (shift_assignment_id) REFERENCES workforce_planning_shift_assignment (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_wp_conflict_hub_resolved ON workforce_planning_conflict (hub_id, is_resolved);
CREATE INDEX IF NOT EXISTS ix_wp_conflict_hub_employee ON workforce_planning_conflict (hub_id, employee_id);
CREATE INDEX IF NOT EXISTS idx_wp_conflict_hub         ON workforce_planning_conflict (hub_id, is_deleted);
