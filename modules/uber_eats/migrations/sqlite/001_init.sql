-- Uber Eats · esquema inicial (SQLite). Portado fielmente de old_modules/m_uber_eats/models.py.
-- Modelos: UEStore (restaurante registrado en Uber), UEOrder (pedido de reparto, idempotente
-- por uber_order_id), UEMenu (menú publicado en Uber) y UEEvent (evento de webhook crudo,
-- idempotente por event_id). Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete
-- + auditoría. Las relaciones FK->store se conservan como TEXT (UUID) con ON DELETE CASCADE.

-- Restaurante registrado en Uber Eats para el hub.
-- store_id es el identificador de Uber, único por hub (ix uq_uber_eats_store_hub_sid).
CREATE TABLE IF NOT EXISTS uber_eats_store (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    store_id      TEXT NOT NULL,                 -- identificador de Uber para la tienda
    name          TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'active', -- active|paused|offline
    country       TEXT NOT NULL DEFAULT 'ES',
    currency      TEXT NOT NULL DEFAULT 'EUR',
    is_active     INTEGER NOT NULL DEFAULT 1,
    last_sync_at  TEXT,                          -- ISO datetime o NULL
    settings      TEXT,                          -- JSON libre o NULL
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_ue_store_hub_sid    ON uber_eats_store (hub_id, store_id);
CREATE INDEX        IF NOT EXISTS ix_ue_store_hub_status ON uber_eats_store (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_ue_store_hub_active ON uber_eats_store (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS idx_uber_eats_store_hub ON uber_eats_store (hub_id, is_deleted);

-- Pedido de reparto recibido de Uber Eats. Idempotente por (hub_id, uber_order_id).
-- order_number es el número interno del hub: UE-YYYYMMDD-NNNN (único por hub).
CREATE TABLE IF NOT EXISTS uber_eats_order (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    store_id        TEXT NOT NULL,                 -- FK -> uber_eats_store.id
    uber_order_id   TEXT NOT NULL,                 -- id del pedido en Uber (idempotencia)
    order_number    TEXT NOT NULL,                 -- UE-YYYYMMDD-NNNN (lado hub)
    customer_name   TEXT NOT NULL DEFAULT '',
    total_amount    NUMERIC NOT NULL DEFAULT 0,
    currency        TEXT NOT NULL DEFAULT 'EUR',
    status          TEXT NOT NULL DEFAULT 'created', -- created|accepted|preparing|ready|delivered|cancelled
    created_at_uber TEXT,                          -- ISO datetime o NULL (cuándo se creó en Uber)
    items           TEXT,                          -- JSON array de líneas o NULL
    customer_notes  TEXT NOT NULL DEFAULT '',
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    FOREIGN KEY (store_id) REFERENCES uber_eats_store (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_ue_order_hub_uid    ON uber_eats_order (hub_id, uber_order_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_ue_order_hub_num    ON uber_eats_order (hub_id, order_number);
CREATE INDEX        IF NOT EXISTS ix_ue_order_hub_status ON uber_eats_order (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_ue_order_hub_store  ON uber_eats_order (hub_id, store_id);
CREATE INDEX        IF NOT EXISTS idx_uber_eats_order_hub ON uber_eats_order (hub_id, is_deleted);

-- Menú publicado en Uber para una tienda. Upsert por (hub_id, uber_menu_id).
CREATE TABLE IF NOT EXISTS uber_eats_menu (
    id             TEXT PRIMARY KEY,
    hub_id         TEXT NOT NULL,
    store_id       TEXT NOT NULL,                 -- FK -> uber_eats_store.id
    uber_menu_id   TEXT NOT NULL,                 -- id del menú en Uber (idempotencia)
    name           TEXT NOT NULL,
    items_count    INTEGER NOT NULL DEFAULT 0,
    last_synced_at TEXT,                          -- ISO datetime o NULL
    sync_status    TEXT NOT NULL DEFAULT 'pending', -- synced|error|pending
    is_deleted     INTEGER NOT NULL DEFAULT 0,
    deleted_at     TEXT,
    created_by     TEXT,
    updated_by     TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT,
    FOREIGN KEY (store_id) REFERENCES uber_eats_store (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_ue_menu_hub_mid    ON uber_eats_menu (hub_id, uber_menu_id);
CREATE INDEX        IF NOT EXISTS ix_ue_menu_hub_store  ON uber_eats_menu (hub_id, store_id);
CREATE INDEX        IF NOT EXISTS ix_ue_menu_hub_status ON uber_eats_menu (hub_id, sync_status);
CREATE INDEX        IF NOT EXISTS idx_uber_eats_menu_hub ON uber_eats_menu (hub_id, is_deleted);

-- Evento crudo de webhook recibido de Uber, persistido para idempotencia + auditoría.
-- Idempotente por (hub_id, event_id).
CREATE TABLE IF NOT EXISTS uber_eats_event (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    store_id     TEXT NOT NULL,                 -- FK -> uber_eats_store.id
    event_type   TEXT NOT NULL,                 -- order_created|order_updated|order_cancelled|menu_published|store_online|store_offline
    event_id     TEXT NOT NULL,                 -- id del evento en Uber (idempotencia)
    occurred_at  TEXT,                          -- ISO datetime o NULL
    processed_at TEXT,                          -- ISO datetime o NULL
    payload      TEXT,                          -- JSON crudo del webhook o NULL
    status       TEXT NOT NULL DEFAULT 'received', -- received|processed|failed
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT,
    FOREIGN KEY (store_id) REFERENCES uber_eats_store (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_ue_event_hub_eid    ON uber_eats_event (hub_id, event_id);
CREATE INDEX        IF NOT EXISTS ix_ue_event_hub_type   ON uber_eats_event (hub_id, event_type);
CREATE INDEX        IF NOT EXISTS ix_ue_event_hub_status ON uber_eats_event (hub_id, status);
CREATE INDEX        IF NOT EXISTS idx_uber_eats_event_hub ON uber_eats_event (hub_id, is_deleted);
