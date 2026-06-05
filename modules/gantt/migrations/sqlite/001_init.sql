-- Gantt · esquema inicial (SQLite). Portado fielmente de old_modules/m_gantt/models.py.
-- Modelos: GanttProject (proyecto de planificación), GanttTask (tarea o hito, con jerarquía)
-- y TaskDependency (arista de dependencia entre dos tareas del mismo proyecto).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Proyecto de planificación: agrupa tareas, hitos y dependencias.
-- progress_pct es agregado (media de las tareas); se recalcula en runtime/WASM.
CREATE TABLE IF NOT EXISTS gantt_project (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    name         TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    start_date   TEXT,                          -- ISO YYYY-MM-DD o NULL
    end_date     TEXT,                          -- ISO YYYY-MM-DD o NULL
    status       TEXT NOT NULL DEFAULT 'planning', -- planning|active|on_hold|completed|cancelled
    color        TEXT NOT NULL DEFAULT '#3b82f6', -- color CSS (hex) de la barra en el timeline
    owner_ref    TEXT,                          -- ref libre de usuario (sin FK)
    progress_pct INTEGER NOT NULL DEFAULT 0,    -- agregado 0-100
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT
);
CREATE INDEX IF NOT EXISTS ix_gantt_project_hub_status ON gantt_project (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_gantt_project_hub_owner  ON gantt_project (hub_id, owner_ref);
CREATE INDEX IF NOT EXISTS idx_gantt_project_hub       ON gantt_project (hub_id, is_deleted);

-- Tarea (o hito) dentro de un proyecto. Soporta jerarquía vía parent_task_id.
-- duration_days se deriva de start/end (0 para hitos); el cálculo va a WASM/runtime.
CREATE TABLE IF NOT EXISTS gantt_task (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    project_id      TEXT NOT NULL,
    name            TEXT NOT NULL,
    start_date      TEXT,                        -- ISO YYYY-MM-DD o NULL
    end_date        TEXT,                        -- ISO YYYY-MM-DD o NULL
    duration_days   INTEGER NOT NULL DEFAULT 0,  -- duración en días (0 para hitos)
    assigned_to_ref TEXT,                        -- ref libre de usuario (sin FK)
    progress_pct    INTEGER NOT NULL DEFAULT 0,  -- 0-100
    is_milestone    INTEGER NOT NULL DEFAULT 0,
    parent_task_id  TEXT,                        -- jerarquía: tarea padre (mismo proyecto)
    "order"         INTEGER NOT NULL DEFAULT 0,  -- orden de presentación
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    FOREIGN KEY (project_id)     REFERENCES gantt_project (id) ON DELETE CASCADE,
    FOREIGN KEY (parent_task_id) REFERENCES gantt_task (id)    ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_gantt_task_hub_project  ON gantt_task (hub_id, project_id);
CREATE INDEX IF NOT EXISTS ix_gantt_task_hub_parent   ON gantt_task (hub_id, parent_task_id);
CREATE INDEX IF NOT EXISTS ix_gantt_task_hub_assigned ON gantt_task (hub_id, assigned_to_ref);
CREATE INDEX IF NOT EXISTS idx_gantt_task_hub         ON gantt_task (hub_id, is_deleted);

-- Dependencia entre dos tareas del mismo proyecto. 4 tipos + lag opcional en días.
CREATE TABLE IF NOT EXISTS gantt_task_dependency (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    predecessor_task_id TEXT NOT NULL,
    successor_task_id   TEXT NOT NULL,
    dependency_type     TEXT NOT NULL DEFAULT 'finish_to_start', -- finish_to_start|start_to_start|finish_to_finish|start_to_finish
    lag_days            INTEGER NOT NULL DEFAULT 0,
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT,
    FOREIGN KEY (predecessor_task_id) REFERENCES gantt_task (id) ON DELETE CASCADE,
    FOREIGN KEY (successor_task_id)   REFERENCES gantt_task (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_gantt_dep_hub_predecessor ON gantt_task_dependency (hub_id, predecessor_task_id);
CREATE INDEX IF NOT EXISTS ix_gantt_dep_hub_successor   ON gantt_task_dependency (hub_id, successor_task_id);
CREATE INDEX IF NOT EXISTS idx_gantt_task_dependency_hub ON gantt_task_dependency (hub_id, is_deleted);
