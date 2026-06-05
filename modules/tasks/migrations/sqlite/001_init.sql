-- Tasks · esquema inicial (SQLite). Portado fielmente de old_modules/m_tasks/models.py.
-- Modelos: TaskProject (agrupación de tareas), Task (unidad de trabajo con estado/prioridad/
-- vencimiento/subtareas), TaskComment (comentario hilado) y TaskCounter (secuencia atómica
-- por hub+día para task_number). Contrato de fila estándar de hub-next (§2.5):
-- hub_id + soft-delete + auditoría.

-- Proyecto: bucket de agrupación de tareas (p.ej. "Auditoría Q3", "Apertura tienda").
-- code es único por hub. owner_ref es una referencia laxa al LocalUser (sin FK cruzada).
CREATE TABLE IF NOT EXISTS tasks_project (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    code        TEXT NOT NULL,
    name        TEXT NOT NULL,
    color       TEXT NOT NULL DEFAULT '',
    is_active   INTEGER NOT NULL DEFAULT 1,
    owner_ref   TEXT,                          -- uuid de LocalUser o NULL (ref laxa)
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_task_project_hub_code   ON tasks_project (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_task_project_hub_active ON tasks_project (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS idx_tasks_project_hub      ON tasks_project (hub_id, is_deleted);

-- Tarea: unidad de trabajo. task_number autogenerado por hub (TSK-YYYYMMDD-NNNN), único por hub.
-- status ∈ todo|in_progress|blocked|done|cancelled. priority ∈ low|medium|high|urgent.
-- assigned_to_ref/created_by_ref son referencias laxas a LocalUser (sin FK cruzada).
-- parent_task_id permite jerarquía de subtareas (FK a la propia tabla). tags es JSON.
CREATE TABLE IF NOT EXISTS tasks_task (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    task_number     TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    project_id      TEXT,                      -- FK a tasks_project (SET NULL al borrar)
    status          TEXT NOT NULL DEFAULT 'todo',
    priority        TEXT NOT NULL DEFAULT 'medium',
    assigned_to_ref TEXT,                      -- uuid de LocalUser o NULL (ref laxa)
    created_by_ref  TEXT,                      -- uuid de LocalUser o NULL (ref laxa)
    due_date        TEXT,                      -- ISO datetime o NULL
    completed_at    TEXT,                      -- ISO datetime o NULL (sellado al marcar done)
    parent_task_id  TEXT,                      -- FK a tasks_task (subtarea)
    tags            TEXT NOT NULL DEFAULT '[]', -- JSON: lista de etiquetas libres
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    FOREIGN KEY (project_id)     REFERENCES tasks_project (id) ON DELETE SET NULL,
    FOREIGN KEY (parent_task_id) REFERENCES tasks_task (id)    ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_task_hub_number   ON tasks_task (hub_id, task_number);
CREATE INDEX        IF NOT EXISTS ix_task_hub_status    ON tasks_task (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_task_hub_assigned  ON tasks_task (hub_id, assigned_to_ref);
CREATE INDEX        IF NOT EXISTS ix_task_hub_due       ON tasks_task (hub_id, due_date);
CREATE INDEX        IF NOT EXISTS ix_task_hub_project   ON tasks_task (hub_id, project_id);
CREATE INDEX        IF NOT EXISTS ix_task_hub_parent    ON tasks_task (hub_id, parent_task_id);
CREATE INDEX        IF NOT EXISTS idx_tasks_task_hub    ON tasks_task (hub_id, is_deleted);

-- Comentario hilado sobre una tarea. author_ref es referencia laxa a LocalUser.
CREATE TABLE IF NOT EXISTS tasks_comment (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    task_id     TEXT NOT NULL,                 -- FK a tasks_task (CASCADE al borrar)
    author_ref  TEXT,                          -- uuid de LocalUser o NULL (ref laxa)
    comment     TEXT NOT NULL,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks_task (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_task_comment_hub_task ON tasks_comment (hub_id, task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_comment_hub    ON tasks_comment (hub_id, is_deleted);

-- Contador atómico por (hub, día) para generar task_number sin carrera SELECT→UPDATE.
-- Se escribe vía UPSERT (INSERT ... ON CONFLICT DO UPDATE ... RETURNING) desde el runtime.
CREATE TABLE IF NOT EXISTS tasks_counter (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    day         TEXT NOT NULL,                 -- YYYYMMDD
    last_number INTEGER NOT NULL DEFAULT 0,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_task_counter_hub_day ON tasks_counter (hub_id, day);
CREATE INDEX        IF NOT EXISTS idx_tasks_counter_hub   ON tasks_counter (hub_id, is_deleted);
