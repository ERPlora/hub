-- Communications · esquema inicial (SQLite). Portado de old_modules/m_communications/models.py.
-- Inbox multicanal unificado: cuentas, grupos de enrutado, hilos, mensajes, adjuntos,
-- reglas de enrutado, auditoría de asignaciones, envíos programados, plantillas y ajustes.
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.
-- Nota: los campos JSON (etiquetas, direcciones, condiciones) se almacenan como TEXT JSON.
-- Los campos cifrados (passwords IMAP/SMTP, tokens OAuth) los gestiona el runtime/host;
-- aquí se guardan ya cifrados como TEXT. Ver WASM-TODO.md.

-- ==========================================================================
-- CUENTA: email o cuenta social conectada para el inbox.
-- account_type: hub (compartida) | user (privada). channel: email|whatsapp|instagram|facebook.
-- ==========================================================================
CREATE TABLE IF NOT EXISTS communications_account (
    id                      TEXT PRIMARY KEY,
    hub_id                  TEXT NOT NULL,
    name                    TEXT NOT NULL,
    account_type            TEXT NOT NULL DEFAULT 'hub',     -- hub|user
    channel                 TEXT NOT NULL DEFAULT 'email',   -- email|whatsapp|instagram|facebook
    owner_id                TEXT,
    email_address           TEXT NOT NULL DEFAULT '',
    imap_host               TEXT NOT NULL DEFAULT '',
    imap_port               INTEGER NOT NULL DEFAULT 993,
    imap_username           TEXT NOT NULL DEFAULT '',
    imap_password_encrypted TEXT NOT NULL DEFAULT '',
    imap_use_ssl            INTEGER NOT NULL DEFAULT 1,
    smtp_host               TEXT NOT NULL DEFAULT '',
    smtp_port               INTEGER NOT NULL DEFAULT 587,
    smtp_username           TEXT NOT NULL DEFAULT '',
    smtp_password_encrypted TEXT NOT NULL DEFAULT '',
    smtp_use_tls            INTEGER NOT NULL DEFAULT 1,
    external_account_id     TEXT NOT NULL DEFAULT '',
    access_token_encrypted  TEXT NOT NULL DEFAULT '',
    token_expires_at        TEXT,
    is_active               INTEGER NOT NULL DEFAULT 1,
    last_sync_at            TEXT,
    sync_status             TEXT NOT NULL DEFAULT 'idle',     -- idle|syncing|error
    sync_error              TEXT NOT NULL DEFAULT '',
    is_deleted              INTEGER NOT NULL DEFAULT 0,
    deleted_at              TEXT,
    created_by              TEXT,
    updated_by              TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT
);
CREATE INDEX IF NOT EXISTS ix_comm_account_hub_channel ON communications_account (hub_id, channel);
CREATE INDEX IF NOT EXISTS ix_comm_account_hub_type    ON communications_account (hub_id, account_type);
CREATE INDEX IF NOT EXISTS idx_communications_account_hub ON communications_account (hub_id, is_deleted);

-- ==========================================================================
-- GRUPO: área organizativa para enrutar hilos. source: blueprint|custom.
-- ==========================================================================
CREATE TABLE IF NOT EXISTS communications_group (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    icon        TEXT NOT NULL DEFAULT 'people-outline',
    color       TEXT NOT NULL DEFAULT '#6366f1',
    is_active   INTEGER NOT NULL DEFAULT 1,
    is_default  INTEGER NOT NULL DEFAULT 0,
    is_system   INTEGER NOT NULL DEFAULT 0,
    source      TEXT NOT NULL DEFAULT 'custom',    -- blueprint|custom
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS ix_comm_group_hub_active ON communications_group (hub_id, is_active);
CREATE INDEX IF NOT EXISTS idx_communications_group_hub ON communications_group (hub_id, is_deleted);

-- ==========================================================================
-- MIEMBRO DE GRUPO (M2M usuario↔grupo). role: member|lead.
-- ==========================================================================
CREATE TABLE IF NOT EXISTS communications_group_member (
    id         TEXT PRIMARY KEY,
    hub_id     TEXT NOT NULL,
    group_id   TEXT NOT NULL,
    user_id    TEXT NOT NULL,
    role       TEXT NOT NULL DEFAULT 'member',     -- member|lead
    is_deleted INTEGER NOT NULL DEFAULT 0,
    deleted_at TEXT,
    created_by TEXT,
    updated_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    FOREIGN KEY (group_id) REFERENCES communications_group (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_comm_group_member_unique ON communications_group_member (hub_id, group_id, user_id);
CREATE INDEX IF NOT EXISTS ix_comm_group_member_group ON communications_group_member (group_id);
CREATE INDEX IF NOT EXISTS idx_communications_group_member_hub ON communications_group_member (hub_id, is_deleted);

-- ==========================================================================
-- CUENTA↔GRUPO (M2M).
-- ==========================================================================
CREATE TABLE IF NOT EXISTS communications_account_group (
    id         TEXT PRIMARY KEY,
    hub_id     TEXT NOT NULL,
    account_id TEXT NOT NULL,
    group_id   TEXT NOT NULL,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    deleted_at TEXT,
    created_by TEXT,
    updated_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    FOREIGN KEY (account_id) REFERENCES communications_account (id) ON DELETE CASCADE,
    FOREIGN KEY (group_id)   REFERENCES communications_group (id)   ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_comm_account_group_unique ON communications_account_group (hub_id, account_id, group_id);
CREATE INDEX IF NOT EXISTS idx_communications_account_group_hub ON communications_account_group (hub_id, is_deleted);

-- ==========================================================================
-- HILO: conversación unificada (cadena de email, chat, DM).
-- status: open|snoozed|closed|archived|spam. folder: inbox|sent|drafts|archive|spam|trash.
-- ==========================================================================
CREATE TABLE IF NOT EXISTS communications_thread (
    id                 TEXT PRIMARY KEY,
    hub_id             TEXT NOT NULL,
    account_id         TEXT,
    channel            TEXT NOT NULL DEFAULT 'email',
    contact_identifier TEXT NOT NULL DEFAULT '',
    contact_name       TEXT NOT NULL DEFAULT '',
    customer_id        TEXT,
    subject            TEXT NOT NULL DEFAULT '',
    status             TEXT NOT NULL DEFAULT 'open',     -- open|snoozed|closed|archived|spam
    priority           TEXT NOT NULL DEFAULT 'normal',   -- low|normal|high|urgent
    assigned_to_id     TEXT,
    group_id           TEXT,
    folder             TEXT NOT NULL DEFAULT 'inbox',    -- inbox|sent|drafts|archive|spam|trash
    last_message_at    TEXT,
    unread_count       INTEGER NOT NULL DEFAULT 0,
    message_count      INTEGER NOT NULL DEFAULT 0,
    labels             TEXT NOT NULL DEFAULT '[]',       -- JSON array
    metadata           TEXT NOT NULL DEFAULT '{}',       -- JSON object
    source_module      TEXT NOT NULL DEFAULT '',
    source_id          TEXT,
    snoozed_until      TEXT,
    is_deleted         INTEGER NOT NULL DEFAULT 0,
    deleted_at         TEXT,
    created_by         TEXT,
    updated_by         TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT,
    FOREIGN KEY (account_id) REFERENCES communications_account (id) ON DELETE SET NULL,
    FOREIGN KEY (group_id)   REFERENCES communications_group (id)   ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_comm_thread_hub_status   ON communications_thread (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_comm_thread_hub_folder   ON communications_thread (hub_id, folder);
CREATE INDEX IF NOT EXISTS ix_comm_thread_hub_group    ON communications_thread (hub_id, group_id);
CREATE INDEX IF NOT EXISTS ix_comm_thread_hub_assigned ON communications_thread (hub_id, assigned_to_id);
CREATE INDEX IF NOT EXISTS ix_comm_thread_hub_last_msg ON communications_thread (hub_id, last_message_at);
CREATE INDEX IF NOT EXISTS ix_comm_thread_contact      ON communications_thread (hub_id, contact_identifier);
CREATE INDEX IF NOT EXISTS idx_communications_thread_hub ON communications_thread (hub_id, is_deleted);

-- ==========================================================================
-- MENSAJE: mensaje individual dentro de un hilo.
-- direction: inbound|outbound. status: received|draft|queued|sent|delivered|read|failed.
-- ==========================================================================
CREATE TABLE IF NOT EXISTS communications_message (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    thread_id           TEXT NOT NULL,
    direction           TEXT NOT NULL DEFAULT 'inbound',  -- inbound|outbound
    message_type        TEXT NOT NULL DEFAULT 'text',     -- text|html|image|document
    sender_address      TEXT NOT NULL DEFAULT '',
    sender_name         TEXT NOT NULL DEFAULT '',
    recipient_addresses TEXT NOT NULL DEFAULT '[]',       -- JSON array
    cc_addresses        TEXT NOT NULL DEFAULT '[]',       -- JSON array
    bcc_addresses       TEXT NOT NULL DEFAULT '[]',       -- JSON array
    subject             TEXT NOT NULL DEFAULT '',
    body_text           TEXT NOT NULL DEFAULT '',
    body_html           TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'received',
    message_id_header   TEXT NOT NULL DEFAULT '',
    in_reply_to         TEXT NOT NULL DEFAULT '',
    "references"        TEXT NOT NULL DEFAULT '',
    external_id         TEXT NOT NULL DEFAULT '',
    metadata            TEXT NOT NULL DEFAULT '{}',       -- JSON object
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT,
    FOREIGN KEY (thread_id) REFERENCES communications_thread (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_comm_message_thread     ON communications_message (thread_id);
CREATE INDEX IF NOT EXISTS ix_comm_message_hub_status ON communications_message (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_comm_message_external   ON communications_message (hub_id, external_id);
CREATE INDEX IF NOT EXISTS idx_communications_message_hub ON communications_message (hub_id, is_deleted);

-- ==========================================================================
-- ADJUNTO: fichero adjunto de un mensaje.
-- ==========================================================================
CREATE TABLE IF NOT EXISTS communications_message_attachment (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    message_id   TEXT NOT NULL,
    filename     TEXT NOT NULL DEFAULT '',
    content_type TEXT NOT NULL DEFAULT '',
    size_bytes   INTEGER NOT NULL DEFAULT 0,
    storage_key  TEXT NOT NULL DEFAULT '',
    is_inline    INTEGER NOT NULL DEFAULT 0,
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT,
    FOREIGN KEY (message_id) REFERENCES communications_message (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_comm_attachment_message ON communications_message_attachment (message_id);
CREATE INDEX IF NOT EXISTS idx_communications_message_attachment_hub ON communications_message_attachment (hub_id, is_deleted);

-- ==========================================================================
-- REGLA DE ENRUTADO: condiciones (JSON) → grupo + auto-acciones. priority asc.
-- ==========================================================================
CREATE TABLE IF NOT EXISTS communications_routing_rule (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    group_id          TEXT NOT NULL,
    name              TEXT NOT NULL,
    priority          INTEGER NOT NULL DEFAULT 0,
    is_active         INTEGER NOT NULL DEFAULT 1,
    conditions        TEXT NOT NULL DEFAULT '{}',   -- JSON object
    auto_assign_to_id TEXT,
    auto_label        TEXT NOT NULL DEFAULT '[]',   -- JSON array
    auto_priority     TEXT NOT NULL DEFAULT '',
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    FOREIGN KEY (group_id) REFERENCES communications_group (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_comm_routing_hub_active   ON communications_routing_rule (hub_id, is_active);
CREATE INDEX IF NOT EXISTS ix_comm_routing_hub_priority ON communications_routing_rule (hub_id, priority);
CREATE INDEX IF NOT EXISTS idx_communications_routing_rule_hub ON communications_routing_rule (hub_id, is_deleted);

-- ==========================================================================
-- ASIGNACIÓN DE HILO (auditoría de transferencias/asignaciones).
-- assignment_type: auto_route|manual_assign|transfer|escalate.
-- ==========================================================================
CREATE TABLE IF NOT EXISTS communications_thread_assignment (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    thread_id       TEXT NOT NULL,
    from_group_id   TEXT,
    to_group_id     TEXT,
    from_user_id    TEXT,
    to_user_id      TEXT,
    assigned_by_id  TEXT,
    note            TEXT NOT NULL DEFAULT '',
    assignment_type TEXT NOT NULL DEFAULT 'manual_assign',
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    FOREIGN KEY (thread_id) REFERENCES communications_thread (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_comm_assignment_thread      ON communications_thread_assignment (thread_id);
CREATE INDEX IF NOT EXISTS ix_comm_assignment_hub_created ON communications_thread_assignment (hub_id, created_at);
CREATE INDEX IF NOT EXISTS idx_communications_thread_assignment_hub ON communications_thread_assignment (hub_id, is_deleted);

-- ==========================================================================
-- MENSAJE PROGRAMADO: email para envío futuro. status: pending|sent|failed|cancelled.
-- ==========================================================================
CREATE TABLE IF NOT EXISTS communications_scheduled_message (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    thread_id           TEXT,
    account_id          TEXT NOT NULL,
    recipient_addresses TEXT NOT NULL DEFAULT '[]',   -- JSON array
    cc_addresses        TEXT NOT NULL DEFAULT '[]',   -- JSON array
    bcc_addresses       TEXT NOT NULL DEFAULT '[]',   -- JSON array
    subject             TEXT NOT NULL DEFAULT '',
    body_text           TEXT NOT NULL DEFAULT '',
    body_html           TEXT NOT NULL DEFAULT '',
    attachments         TEXT NOT NULL DEFAULT '[]',   -- JSON array
    scheduled_at        TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending',  -- pending|sent|failed|cancelled
    sent_at             TEXT,
    error_message       TEXT NOT NULL DEFAULT '',
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT,
    FOREIGN KEY (thread_id)  REFERENCES communications_thread (id)  ON DELETE SET NULL,
    FOREIGN KEY (account_id) REFERENCES communications_account (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_comm_scheduled_hub_status ON communications_scheduled_message (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_comm_scheduled_pending    ON communications_scheduled_message (hub_id, status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_communications_scheduled_message_hub ON communications_scheduled_message (hub_id, is_deleted);

-- ==========================================================================
-- PLANTILLA DE EMAIL: plantilla reutilizable con variables de sustitución.
-- ==========================================================================
CREATE TABLE IF NOT EXISTS communications_email_template (
    id         TEXT PRIMARY KEY,
    hub_id     TEXT NOT NULL,
    name       TEXT NOT NULL,
    subject    TEXT NOT NULL DEFAULT '',
    body_html  TEXT NOT NULL DEFAULT '',
    body_text  TEXT NOT NULL DEFAULT '',
    variables  TEXT NOT NULL DEFAULT '[]',   -- JSON array de nombres de variable
    is_active  INTEGER NOT NULL DEFAULT 1,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    deleted_at TEXT,
    created_by TEXT,
    updated_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_comm_email_template_hub      ON communications_email_template (hub_id);
CREATE INDEX IF NOT EXISTS ix_comm_email_template_hub_name ON communications_email_template (hub_id, name);
CREATE INDEX IF NOT EXISTS idx_communications_email_template_hub ON communications_email_template (hub_id, is_deleted);

-- ==========================================================================
-- AJUSTES (singleton por hub): general, enrutado AI, sync, auto-cierre,
-- notificaciones y footer/firma de email. Una fila por hub_id.
-- ==========================================================================
CREATE TABLE IF NOT EXISTS communications_settings (
    id                          TEXT PRIMARY KEY,
    hub_id                      TEXT NOT NULL,
    is_enabled                  INTEGER NOT NULL DEFAULT 1,
    gpt_routing_enabled         INTEGER NOT NULL DEFAULT 0,
    gpt_routing_prompt          TEXT NOT NULL DEFAULT '',
    email_sync_interval_seconds INTEGER NOT NULL DEFAULT 60,
    email_max_sync_days         INTEGER NOT NULL DEFAULT 30,
    auto_close_hours            INTEGER NOT NULL DEFAULT 0,
    notify_on_new_thread        INTEGER NOT NULL DEFAULT 1,
    notify_on_assignment        INTEGER NOT NULL DEFAULT 1,
    footer_enabled              INTEGER NOT NULL DEFAULT 0,
    footer_html                 TEXT NOT NULL DEFAULT '',
    footer_include_logo         INTEGER NOT NULL DEFAULT 1,
    footer_logo_url             TEXT NOT NULL DEFAULT '',
    footer_company_name         TEXT NOT NULL DEFAULT '',
    footer_address              TEXT NOT NULL DEFAULT '',
    footer_phone                TEXT NOT NULL DEFAULT '',
    footer_website              TEXT NOT NULL DEFAULT '',
    footer_social_links         TEXT NOT NULL DEFAULT '{}',   -- JSON object
    is_deleted                  INTEGER NOT NULL DEFAULT 0,
    deleted_at                  TEXT,
    created_by                  TEXT,
    updated_by                  TEXT,
    created_at                  TEXT NOT NULL,
    updated_at                  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_comm_settings_hub ON communications_settings (hub_id);
CREATE INDEX IF NOT EXISTS idx_communications_settings_hub ON communications_settings (hub_id, is_deleted);
