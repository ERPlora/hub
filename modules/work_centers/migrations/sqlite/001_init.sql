-- Work Centers · esquema inicial (SQLite). Portado fielmente de old_modules/m_work_centers/models.py.
-- Modelos: WorkCenter (centro de producción: máquina/línea/estación/celda) y
-- WorkCenterEvent (evento de runtime: run/stop/breakdown/setup/maintenance/idle) usados
-- para calcular utilización y OEE.
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Centro de producción. code es único por hub (identificador estable de negocio).
-- calendar es JSON libre con el horario/turnos (p.ej. {"mon":["08:00-16:00"]}).
CREATE TABLE IF NOT EXISTS work_centers_center (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    code              TEXT NOT NULL,
    name              TEXT NOT NULL,
    center_type       TEXT NOT NULL DEFAULT 'machine',   -- machine|line|station|cell
    capacity_per_hour NUMERIC NOT NULL DEFAULT 0,         -- rendimiento teórico (uds/hora)
    hourly_cost       NUMERIC NOT NULL DEFAULT 0,         -- coste por hora de marcha (moneda hub)
    location_ref      TEXT NOT NULL DEFAULT '',           -- ref libre a ubicación física
    is_active         INTEGER NOT NULL DEFAULT 1,
    calendar          TEXT NOT NULL DEFAULT '{}',         -- JSON con turnos/horario
    notes             TEXT NOT NULL DEFAULT '',
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_wc_hub_code   ON work_centers_center (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_wc_hub_active  ON work_centers_center (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS ix_wc_hub_type    ON work_centers_center (hub_id, center_type);
CREATE INDEX        IF NOT EXISTS idx_work_centers_center_hub ON work_centers_center (hub_id, is_deleted);

-- Evento de runtime sobre un centro. duration_minutes se calcula al cerrar el evento
-- (o se deriva de la duración suministrada). ended_at NULL = evento abierto (en curso).
-- operator_ref es ref libre a un usuario/operario (string hasta tener FK a staff).
CREATE TABLE IF NOT EXISTS work_centers_event (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    work_center_id   TEXT NOT NULL,
    event_type       TEXT NOT NULL DEFAULT 'run',         -- run|stop|breakdown|setup|maintenance|idle
    started_at       TEXT NOT NULL,                       -- ISO datetime
    ended_at         TEXT,                                -- ISO datetime o NULL (abierto)
    duration_minutes INTEGER,                             -- minutos enteros o NULL
    reason           TEXT NOT NULL DEFAULT '',
    operator_ref     TEXT NOT NULL DEFAULT '',
    notes            TEXT NOT NULL DEFAULT '',
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT,
    FOREIGN KEY (work_center_id) REFERENCES work_centers_center (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_wce_hub_center      ON work_centers_event (hub_id, work_center_id);
CREATE INDEX IF NOT EXISTS ix_wce_hub_event_type  ON work_centers_event (hub_id, event_type);
CREATE INDEX IF NOT EXISTS ix_wce_started_at       ON work_centers_event (started_at);
CREATE INDEX IF NOT EXISTS idx_work_centers_event_hub ON work_centers_event (hub_id, is_deleted);
