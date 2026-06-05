-- Messaging · esquema inicial (SQLite). Portado fielmente de old_modules/m_messaging/models.py.
-- Comunicación con clientes vía WhatsApp, SMS y email + automatizaciones CRM.
-- Modelos: MessagingSettings (config por hub), MessageTemplate (plantillas con variables),
-- Message (log de envíos), Campaign (envíos masivos), MessageAutomation (reglas por evento),
-- AutomationExecution (log de ejecuciones).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.
-- NOTA: customer_id se guarda como TEXT plano (referencia lógica a customers_customer,
-- tabla de OTRO módulo) — sin FOREIGN KEY cross-módulo.

-- Configuración de mensajería por hub (singleton por hub_id).
CREATE TABLE IF NOT EXISTS messaging_settings (
    id                            TEXT PRIMARY KEY,
    hub_id                        TEXT NOT NULL,
    -- WhatsApp
    whatsapp_enabled              INTEGER NOT NULL DEFAULT 0,
    whatsapp_api_token            TEXT NOT NULL DEFAULT '',
    whatsapp_phone_id             TEXT NOT NULL DEFAULT '',
    whatsapp_business_id          TEXT NOT NULL DEFAULT '',
    -- SMS
    sms_enabled                   INTEGER NOT NULL DEFAULT 0,
    sms_provider                  TEXT NOT NULL DEFAULT 'none',  -- none|twilio|messagebird
    sms_api_key                   TEXT NOT NULL DEFAULT '',
    sms_sender_name               TEXT NOT NULL DEFAULT '',
    -- Email
    email_enabled                 INTEGER NOT NULL DEFAULT 1,
    email_from_name               TEXT NOT NULL DEFAULT '',
    email_from_address            TEXT NOT NULL DEFAULT '',
    email_smtp_host               TEXT NOT NULL DEFAULT '',
    email_smtp_port               INTEGER NOT NULL DEFAULT 587,
    email_smtp_username           TEXT NOT NULL DEFAULT '',
    email_smtp_password           TEXT NOT NULL DEFAULT '',
    email_smtp_use_tls            INTEGER NOT NULL DEFAULT 1,
    -- Automatización
    appointment_reminder_enabled  INTEGER NOT NULL DEFAULT 0,
    appointment_reminder_hours    INTEGER NOT NULL DEFAULT 24,
    booking_confirmation_enabled  INTEGER NOT NULL DEFAULT 1,
    -- Contrato estándar
    is_deleted                    INTEGER NOT NULL DEFAULT 0,
    deleted_at                    TEXT,
    created_by                    TEXT,
    created_at                    TEXT NOT NULL,
    updated_by                    TEXT,
    updated_at                    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_messaging_settings_hub ON messaging_settings (hub_id);
CREATE INDEX        IF NOT EXISTS idx_messaging_settings_hub ON messaging_settings (hub_id, is_deleted);

-- Plantilla reutilizable con placeholders {{variable}}.
CREATE TABLE IF NOT EXISTS messaging_template (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    name        TEXT NOT NULL,
    channel     TEXT NOT NULL DEFAULT 'all',     -- whatsapp|sms|email|all
    category    TEXT NOT NULL DEFAULT 'custom',  -- appointment_reminder|booking_confirmation|receipt|marketing|custom
    subject     TEXT NOT NULL DEFAULT '',
    body        TEXT NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1,
    is_system   INTEGER NOT NULL DEFAULT 0,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_by  TEXT,
    updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_messaging_template_hub     ON messaging_template (hub_id, is_deleted);
CREATE INDEX IF NOT EXISTS ix_messaging_template_channel  ON messaging_template (hub_id, channel);

-- Log de mensajes enviados.
CREATE TABLE IF NOT EXISTS messaging_message (
    id                 TEXT PRIMARY KEY,
    hub_id             TEXT NOT NULL,
    channel            TEXT NOT NULL,                -- whatsapp|sms|email
    recipient_name     TEXT NOT NULL DEFAULT '',
    recipient_contact  TEXT NOT NULL,
    subject            TEXT NOT NULL DEFAULT '',
    body               TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'queued', -- queued|sent|delivered|failed|read
    template_id        TEXT,                          -- ref. lógica messaging_template.id
    customer_id        TEXT,                          -- ref. lógica customers_customer.id (otro módulo)
    sent_at            TEXT,
    delivered_at       TEXT,
    read_at            TEXT,
    error_message      TEXT NOT NULL DEFAULT '',
    external_id        TEXT NOT NULL DEFAULT '',
    extra_metadata     TEXT NOT NULL DEFAULT '{}',    -- JSON
    is_deleted         INTEGER NOT NULL DEFAULT 0,
    deleted_at         TEXT,
    created_by         TEXT,
    created_at         TEXT NOT NULL,
    updated_by         TEXT,
    updated_at         TEXT
);
CREATE INDEX IF NOT EXISTS idx_messaging_message_hub                ON messaging_message (hub_id, is_deleted);
CREATE INDEX IF NOT EXISTS ix_messaging_message_hub_channel_status  ON messaging_message (hub_id, channel, status, created_at);

-- Campañas de envío masivo.
CREATE TABLE IF NOT EXISTS messaging_campaign (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    name             TEXT NOT NULL,
    description      TEXT NOT NULL DEFAULT '',
    channel          TEXT NOT NULL,                 -- whatsapp|sms|email
    template_id      TEXT,                          -- ref. lógica messaging_template.id
    status           TEXT NOT NULL DEFAULT 'draft', -- draft|scheduled|sending|completed|cancelled
    scheduled_at     TEXT,
    started_at       TEXT,
    completed_at     TEXT,
    total_recipients INTEGER NOT NULL DEFAULT 0,
    sent_count       INTEGER NOT NULL DEFAULT 0,
    delivered_count  INTEGER NOT NULL DEFAULT 0,
    failed_count     INTEGER NOT NULL DEFAULT 0,
    target_filter    TEXT NOT NULL DEFAULT '{}',    -- JSON
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_by       TEXT,
    updated_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_messaging_campaign_hub    ON messaging_campaign (hub_id, is_deleted);
CREATE INDEX IF NOT EXISTS ix_messaging_campaign_status  ON messaging_campaign (hub_id, status);

-- Regla de automatización disparada por eventos CRM.
CREATE TABLE IF NOT EXISTS messaging_automation (
    id                 TEXT PRIMARY KEY,
    hub_id             TEXT NOT NULL,
    name               TEXT NOT NULL,
    description        TEXT NOT NULL DEFAULT '',
    trigger            TEXT NOT NULL,                 -- welcome|birthday|...|custom
    channel            TEXT NOT NULL DEFAULT 'email', -- whatsapp|sms|email|all
    template_id        TEXT,                          -- ref. lógica messaging_template.id
    delay_hours        INTEGER NOT NULL DEFAULT 0,
    is_active          INTEGER NOT NULL DEFAULT 1,
    conditions         TEXT NOT NULL DEFAULT '{}',    -- JSON
    total_sent         INTEGER NOT NULL DEFAULT 0,
    last_triggered_at  TEXT,
    is_deleted         INTEGER NOT NULL DEFAULT 0,
    deleted_at         TEXT,
    created_by         TEXT,
    created_at         TEXT NOT NULL,
    updated_by         TEXT,
    updated_at         TEXT
);
CREATE INDEX IF NOT EXISTS idx_messaging_automation_hub      ON messaging_automation (hub_id, is_deleted);
CREATE INDEX IF NOT EXISTS ix_messaging_automation_trigger   ON messaging_automation (hub_id, trigger);
CREATE INDEX IF NOT EXISTS ix_messaging_automation_active    ON messaging_automation (hub_id, is_active);

-- Log de ejecuciones de automatizaciones.
CREATE TABLE IF NOT EXISTS messaging_automation_execution (
    id             TEXT PRIMARY KEY,
    hub_id         TEXT NOT NULL,
    automation_id  TEXT NOT NULL,                 -- ref. lógica messaging_automation.id (mismo módulo)
    customer_id    TEXT,                          -- ref. lógica customers_customer.id (otro módulo)
    message_id     TEXT,                          -- ref. lógica messaging_message.id (mismo módulo)
    status         TEXT NOT NULL DEFAULT 'pending', -- pending|sent|failed|skipped
    trigger_data   TEXT NOT NULL DEFAULT '{}',    -- JSON
    error_message  TEXT NOT NULL DEFAULT '',
    scheduled_for  TEXT,
    executed_at    TEXT,
    is_deleted     INTEGER NOT NULL DEFAULT 0,
    deleted_at     TEXT,
    created_by     TEXT,
    created_at     TEXT NOT NULL,
    updated_by     TEXT,
    updated_at     TEXT,
    FOREIGN KEY (automation_id) REFERENCES messaging_automation (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messaging_automation_execution_hub        ON messaging_automation_execution (hub_id, is_deleted);
CREATE INDEX IF NOT EXISTS ix_messaging_automation_execution_automation  ON messaging_automation_execution (hub_id, automation_id);
