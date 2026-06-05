-- Tickets · esquema inicial (SQLite). Portado fielmente de old_modules/m_tickets/models.py.
-- Modelos: SLA (objetivo de tiempos por prioridad), Ticket (ticket de soporte con
-- máquina de estados y seguimiento SLA) y TicketComment (comentario hilado público/interno).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Objetivo de nivel de servicio (SLA) ligado a un bucket de prioridad.
-- response/resolution en horas; is_active filtra los vigentes.
CREATE TABLE IF NOT EXISTS tickets_sla (
    id                    TEXT PRIMARY KEY,
    hub_id                TEXT NOT NULL,
    name                  TEXT NOT NULL,
    description           TEXT NOT NULL DEFAULT '',
    priority              TEXT NOT NULL DEFAULT 'medium',  -- low|medium|high|urgent
    response_time_hours   INTEGER NOT NULL DEFAULT 24,
    resolution_time_hours INTEGER NOT NULL DEFAULT 72,
    is_active             INTEGER NOT NULL DEFAULT 1,
    is_deleted            INTEGER NOT NULL DEFAULT 0,
    deleted_at            TEXT,
    created_by            TEXT,
    updated_by            TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT
);
CREATE INDEX IF NOT EXISTS ix_tickets_sla_hub_priority ON tickets_sla (hub_id, priority);
CREATE INDEX IF NOT EXISTS ix_tickets_sla_hub_active   ON tickets_sla (hub_id, is_active);
CREATE INDEX IF NOT EXISTS idx_tickets_sla_hub         ON tickets_sla (hub_id, is_deleted);

-- Ticket de soporte. ticket_number (TCK-YYYYMMDD-NNNN) es único por hub (lo genera
-- el handler WASM/runtime, ver WASM-TODO). status sigue la máquina de estados.
-- assigned_to_ref / created_by_ref / author_ref son refs sueltas a usuarios (sin FK).
CREATE TABLE IF NOT EXISTS tickets_ticket (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    ticket_number       TEXT NOT NULL,
    subject             TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    customer_name       TEXT NOT NULL,
    customer_email      TEXT NOT NULL DEFAULT '',
    customer_phone      TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'open',     -- open|in_progress|waiting_customer|resolved|closed|cancelled
    priority            TEXT NOT NULL DEFAULT 'medium',   -- low|medium|high|urgent
    category            TEXT NOT NULL DEFAULT 'general',  -- general|billing|technical|feature_request
    assigned_to_ref     TEXT,
    created_by_ref      TEXT,
    sla_id              TEXT,
    opened_at           TEXT,
    first_response_at   TEXT,
    resolved_at         TEXT,
    closed_at           TEXT,
    satisfaction_rating INTEGER,
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT,
    FOREIGN KEY (sla_id) REFERENCES tickets_sla (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_tickets_ticket_hub_number   ON tickets_ticket (hub_id, ticket_number);
CREATE INDEX        IF NOT EXISTS ix_tickets_ticket_hub_status   ON tickets_ticket (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_tickets_ticket_hub_priority ON tickets_ticket (hub_id, priority);
CREATE INDEX        IF NOT EXISTS ix_tickets_ticket_hub_assigned ON tickets_ticket (hub_id, assigned_to_ref);
CREATE INDEX        IF NOT EXISTS idx_tickets_ticket_hub         ON tickets_ticket (hub_id, is_deleted);

-- Comentario hilado de un ticket: respuesta pública o nota interna (is_internal).
-- Pertenece a un ticket (FK CASCADE). El primer comentario público marca first_response_at
-- en el ticket (lo gestiona el handler WASM/runtime, ver WASM-TODO).
CREATE TABLE IF NOT EXISTS tickets_comment (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    ticket_id    TEXT NOT NULL,
    author_ref   TEXT,
    comment_text TEXT NOT NULL,
    is_internal  INTEGER NOT NULL DEFAULT 0,
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT,
    FOREIGN KEY (ticket_id) REFERENCES tickets_ticket (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_tickets_comment_ticket ON tickets_comment (ticket_id);
CREATE INDEX IF NOT EXISTS idx_tickets_comment_hub   ON tickets_comment (hub_id, is_deleted);
