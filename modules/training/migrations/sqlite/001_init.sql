-- Training & Skills · esquema inicial (SQLite). Portado fielmente de old_modules/m_training/models.py.
-- Modelos: TrainingSettings (config singleton por hub), TrainingProgram (programas de formación),
-- Skill (catálogo de habilidades), EmployeeTraining (inscripciones de empleado en programa) y
-- EmployeeSkill (nivel de competencia de un empleado en una habilidad).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.
-- NOTA: employee_id referencia a un StaffMember del módulo `staff` (depends_on). NO se declara FK
-- cross-módulo (cada módulo OWNea sus tablas); la integridad de empleado la valida el runtime/WASM.

-- Configuración de formación por hub (singleton: una fila por hub_id).
CREATE TABLE IF NOT EXISTS training_settings (
    id                              TEXT PRIMARY KEY,
    hub_id                          TEXT NOT NULL,
    require_completion_proof        INTEGER NOT NULL DEFAULT 0,
    auto_assign_mandatory           INTEGER NOT NULL DEFAULT 1,
    reminder_days_before            INTEGER NOT NULL DEFAULT 7,
    certificate_expiry_warning_days INTEGER NOT NULL DEFAULT 30,
    is_deleted                      INTEGER NOT NULL DEFAULT 0,
    deleted_at                      TEXT,
    created_by                      TEXT,
    updated_by                      TEXT,
    created_at                      TEXT NOT NULL,
    updated_at                      TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_training_settings_hub   ON training_settings (hub_id);
CREATE INDEX        IF NOT EXISTS idx_training_settings_hub  ON training_settings (hub_id, is_deleted);

-- Programa de formación: duración, coste, capacidad y obligatoriedad.
CREATE TABLE IF NOT EXISTS training_program (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    name             TEXT NOT NULL,
    description      TEXT NOT NULL DEFAULT '',
    duration_hours   INTEGER NOT NULL DEFAULT 0,
    is_mandatory     INTEGER NOT NULL DEFAULT 0,
    category         TEXT,
    provider         TEXT,
    cost             NUMERIC NOT NULL DEFAULT 0,
    max_participants INTEGER NOT NULL DEFAULT 0,   -- 0 = ilimitado
    is_active        INTEGER NOT NULL DEFAULT 1,
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT
);
CREATE INDEX IF NOT EXISTS ix_training_program_active    ON training_program (hub_id, is_active);
CREATE INDEX IF NOT EXISTS ix_training_program_mandatory ON training_program (hub_id, is_mandatory);
CREATE INDEX IF NOT EXISTS idx_training_program_hub      ON training_program (hub_id, is_deleted);

-- Habilidad rastreable: catálogo de competencias del hub.
CREATE TABLE IF NOT EXISTS training_skill (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    name        TEXT NOT NULL,
    category    TEXT,
    description TEXT,
    is_active   INTEGER NOT NULL DEFAULT 1,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS ix_training_skill_active ON training_skill (hub_id, is_active);
CREATE INDEX IF NOT EXISTS idx_training_skill_hub   ON training_skill (hub_id, is_deleted);

-- Inscripción de un empleado en un programa de formación.
-- status: not_started | in_progress | completed | failed | expired.
CREATE TABLE IF NOT EXISTS training_employee_training (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    employee_id     TEXT NOT NULL,                  -- StaffMember.id (módulo staff)
    employee_name   TEXT NOT NULL,
    program_id      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'not_started',
    start_date      TEXT,                           -- ISO YYYY-MM-DD o NULL
    completion_date TEXT,                           -- ISO YYYY-MM-DD o NULL
    expiry_date     TEXT,                           -- ISO YYYY-MM-DD o NULL
    score           INTEGER,
    certificate_url TEXT,
    notes           TEXT NOT NULL DEFAULT '',
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    FOREIGN KEY (program_id) REFERENCES training_program (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_training_et_employee ON training_employee_training (hub_id, employee_id);
CREATE INDEX IF NOT EXISTS ix_training_et_program  ON training_employee_training (hub_id, program_id);
CREATE INDEX IF NOT EXISTS ix_training_et_status   ON training_employee_training (hub_id, status);
CREATE INDEX IF NOT EXISTS idx_training_et_hub     ON training_employee_training (hub_id, is_deleted);

-- Nivel de competencia de un empleado en una habilidad.
-- proficiency_level: beginner | intermediate | advanced | expert.
-- (employee_id, skill_id) único por hub (un registro por empleado+habilidad).
CREATE TABLE IF NOT EXISTS training_employee_skill (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    employee_id       TEXT NOT NULL,                -- StaffMember.id (módulo staff)
    employee_name     TEXT NOT NULL,
    skill_id          TEXT NOT NULL,
    proficiency_level TEXT NOT NULL DEFAULT 'beginner',
    acquired_date     TEXT,                          -- ISO YYYY-MM-DD o NULL
    notes             TEXT NOT NULL DEFAULT '',
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    FOREIGN KEY (skill_id) REFERENCES training_skill (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_training_es_employee_skill ON training_employee_skill (hub_id, employee_id, skill_id);
CREATE INDEX        IF NOT EXISTS ix_training_es_employee       ON training_employee_skill (hub_id, employee_id);
CREATE INDEX        IF NOT EXISTS ix_training_es_skill          ON training_employee_skill (hub_id, skill_id);
CREATE INDEX        IF NOT EXISTS idx_training_es_hub           ON training_employee_skill (hub_id, is_deleted);
