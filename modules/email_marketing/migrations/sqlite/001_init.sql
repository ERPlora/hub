-- Email Marketing · esquema inicial (SQLite). Portado de old_modules/m_email_marketing/models.py.
-- Modelos: EmailList (lista de destinatarios), EmailSubscriber (dirección suscrita),
-- EmailCampaign (envío draftable/programable) y EmailEvent (tracking por destinatario).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Lista lógica de destinatarios propiedad del hub.
-- total_subscribers es un contador agregado mantenido por el runtime/WASM (alta/baja).
CREATE TABLE IF NOT EXISTS email_marketing_list (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    name              TEXT NOT NULL,
    description       TEXT NOT NULL DEFAULT '',
    is_active         INTEGER NOT NULL DEFAULT 1,
    total_subscribers INTEGER NOT NULL DEFAULT 0,
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT
);
CREATE INDEX IF NOT EXISTS ix_em_list_hub_active     ON email_marketing_list (hub_id, is_active);
CREATE INDEX IF NOT EXISTS ix_em_list_hub_name       ON email_marketing_list (hub_id, name);
CREATE INDEX IF NOT EXISTS idx_email_marketing_list_hub ON email_marketing_list (hub_id, is_deleted);

-- Una dirección de email en una EmailList. status: subscribed|unsubscribed|bounced.
-- El alta idempotente (case-insensitive por lista) la resuelve el runtime/WASM.
CREATE TABLE IF NOT EXISTS email_marketing_subscriber (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    list_id         TEXT NOT NULL,
    email           TEXT NOT NULL,
    first_name      TEXT NOT NULL DEFAULT '',
    last_name       TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'subscribed',  -- subscribed|unsubscribed|bounced
    subscribed_at   TEXT,                                -- ISO datetime o NULL
    unsubscribed_at TEXT,                                -- ISO datetime o NULL
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    FOREIGN KEY (list_id) REFERENCES email_marketing_list (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_em_sub_hub_list   ON email_marketing_subscriber (hub_id, list_id);
CREATE INDEX IF NOT EXISTS ix_em_sub_hub_email  ON email_marketing_subscriber (hub_id, email);
CREATE INDEX IF NOT EXISTS ix_em_sub_hub_status ON email_marketing_subscriber (hub_id, status);
CREATE INDEX IF NOT EXISTS idx_email_marketing_subscriber_hub ON email_marketing_subscriber (hub_id, is_deleted);

-- Campaña: un envío de email apuntando a una EmailList.
-- status: draft|scheduled|sending|sent|cancelled. Los contadores totales (sent/opens/
-- clicks/bounces) los mantiene el runtime/WASM al procesar el envío y los eventos.
CREATE TABLE IF NOT EXISTS email_marketing_campaign (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    name          TEXT NOT NULL,
    subject       TEXT NOT NULL,
    sender_name   TEXT NOT NULL DEFAULT 'ERPlora',
    sender_email  TEXT NOT NULL,
    list_id       TEXT NOT NULL,
    html_content  TEXT NOT NULL DEFAULT '',
    plain_content TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'draft',  -- draft|scheduled|sending|sent|cancelled
    scheduled_for TEXT,                           -- ISO datetime o NULL
    sent_at       TEXT,                           -- ISO datetime o NULL
    total_sent    INTEGER NOT NULL DEFAULT 0,
    total_opens   INTEGER NOT NULL DEFAULT 0,
    total_clicks  INTEGER NOT NULL DEFAULT 0,
    total_bounces INTEGER NOT NULL DEFAULT 0,
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT,
    FOREIGN KEY (list_id) REFERENCES email_marketing_list (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_em_camp_hub_status    ON email_marketing_campaign (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_em_camp_hub_list      ON email_marketing_campaign (hub_id, list_id);
CREATE INDEX IF NOT EXISTS ix_em_camp_hub_scheduled ON email_marketing_campaign (hub_id, scheduled_for);
CREATE INDEX IF NOT EXISTS idx_email_marketing_campaign_hub ON email_marketing_campaign (hub_id, is_deleted);

-- Evento de tracking por (campaña, suscriptor). event_type: sent|open|click|bounce|unsubscribe.
-- Lo escribe el runtime (envío) o los callbacks de tracking del ESP (pixel/redirect/webhook).
CREATE TABLE IF NOT EXISTS email_marketing_event (
    id             TEXT PRIMARY KEY,
    hub_id         TEXT NOT NULL,
    campaign_id    TEXT NOT NULL,
    subscriber_id  TEXT NOT NULL,
    event_type     TEXT NOT NULL,                 -- sent|open|click|bounce|unsubscribe
    occurred_at    TEXT,                          -- ISO datetime o NULL
    event_metadata TEXT,                          -- JSON libre o NULL
    is_deleted     INTEGER NOT NULL DEFAULT 0,
    deleted_at     TEXT,
    created_by     TEXT,
    updated_by     TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT,
    FOREIGN KEY (campaign_id)   REFERENCES email_marketing_campaign (id) ON DELETE CASCADE,
    FOREIGN KEY (subscriber_id) REFERENCES email_marketing_subscriber (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_em_evt_hub_campaign   ON email_marketing_event (hub_id, campaign_id);
CREATE INDEX IF NOT EXISTS ix_em_evt_hub_subscriber ON email_marketing_event (hub_id, subscriber_id);
CREATE INDEX IF NOT EXISTS ix_em_evt_hub_type       ON email_marketing_event (hub_id, event_type);
CREATE INDEX IF NOT EXISTS idx_email_marketing_event_hub ON email_marketing_event (hub_id, is_deleted);
