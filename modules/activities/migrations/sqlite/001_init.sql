-- Activities · esquema inicial (SQLite). Portado fielmente de old_modules/m_activities/models.py.
-- Modelos: Activity (actividad CRM: call/email/meeting/task/note/sms, con ciclo de vida
-- pending→completed/cancelled y enlace libre a una entidad relacionada) y ActivityReminder
-- (recordatorio asociado a una actividad).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Actividad CRM. activity_type ∈ (call|email|meeting|task|note|sms).
-- status ∈ (pending|completed|cancelled); priority ∈ (low|medium|high).
-- El enlace a la entidad relacionada (lead/opportunity/customer/deal) es libre (no FK dura)
-- para mantener los módulos desacoplados: related_entity_type + related_entity_ref.
-- assigned_to_ref / created_by_ref son referencias de usuario libres (no FK a LocalUser).
CREATE TABLE IF NOT EXISTS activities_activity (
    id                   TEXT PRIMARY KEY,
    hub_id               TEXT NOT NULL,
    activity_type        TEXT NOT NULL,                 -- call|email|meeting|task|note|sms
    subject              TEXT NOT NULL,
    description          TEXT NOT NULL DEFAULT '',
    related_entity_type  TEXT NOT NULL DEFAULT '',      -- lead|opportunity|customer|deal|''
    related_entity_ref   TEXT NOT NULL DEFAULT '',
    scheduled_for        TEXT,                          -- ISO datetime o NULL
    completed_at         TEXT,                          -- ISO datetime o NULL
    duration_minutes     INTEGER,
    assigned_to_ref      TEXT NOT NULL DEFAULT '',
    created_by_ref       TEXT NOT NULL DEFAULT '',
    status               TEXT NOT NULL DEFAULT 'pending',
    priority             TEXT NOT NULL DEFAULT 'medium',
    is_deleted           INTEGER NOT NULL DEFAULT 0,
    deleted_at           TEXT,
    created_by           TEXT,
    updated_by           TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT
);
CREATE INDEX IF NOT EXISTS ix_activity_hub_type      ON activities_activity (hub_id, activity_type);
CREATE INDEX IF NOT EXISTS ix_activity_hub_status    ON activities_activity (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_activity_hub_scheduled ON activities_activity (hub_id, scheduled_for);
CREATE INDEX IF NOT EXISTS ix_activity_hub_related   ON activities_activity (hub_id, related_entity_type, related_entity_ref);
CREATE INDEX IF NOT EXISTS ix_activity_hub_assigned  ON activities_activity (hub_id, assigned_to_ref);
CREATE INDEX IF NOT EXISTS idx_activities_activity_hub ON activities_activity (hub_id, is_deleted);

-- Recordatorio asociado a una actividad. Se programa para remind_at; reminder_sent marca
-- si ya se notificó. Borrado en cascada lógico via la actividad propietaria (mismo módulo).
CREATE TABLE IF NOT EXISTS activities_reminder (
    id             TEXT PRIMARY KEY,
    hub_id         TEXT NOT NULL,
    activity_id    TEXT NOT NULL,
    remind_at      TEXT NOT NULL,                       -- ISO datetime
    reminder_sent  INTEGER NOT NULL DEFAULT 0,
    is_deleted     INTEGER NOT NULL DEFAULT 0,
    deleted_at     TEXT,
    created_by     TEXT,
    updated_by     TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT,
    FOREIGN KEY (activity_id) REFERENCES activities_activity (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_reminder_hub_remind     ON activities_reminder (hub_id, remind_at);
CREATE INDEX IF NOT EXISTS ix_reminder_hub_activity   ON activities_reminder (hub_id, activity_id);
CREATE INDEX IF NOT EXISTS idx_activities_reminder_hub ON activities_reminder (hub_id, is_deleted);
