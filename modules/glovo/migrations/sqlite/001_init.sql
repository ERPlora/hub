-- Glovo · esquema inicial (SQLite). Portado fielmente de old_modules/m_glovo/models.py.
-- Conector a Glovo Partners API: tiendas, pedidos entrantes de delivery, sincronizaciones
-- de menú/catálogo y mapeo de productos Glovo↔producto local.
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Tienda/restaurante Glovo registrada en el hub.
-- store_id es el identificador externo de Glovo, único por hub (ix_glovo_store_hub_store_id).
-- settings es JSON libre (credenciales/ajustes del conector) almacenado como TEXT.
CREATE TABLE IF NOT EXISTS glovo_store (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    store_id      TEXT NOT NULL,                 -- id externo de Glovo
    name          TEXT NOT NULL,
    country       TEXT NOT NULL DEFAULT 'ES',
    city          TEXT NOT NULL DEFAULT '',
    glovo_status  TEXT NOT NULL DEFAULT 'offline', -- online|offline|closed
    is_active     INTEGER NOT NULL DEFAULT 1,
    last_sync_at  TEXT,                          -- ISO datetime o NULL
    settings      TEXT NOT NULL DEFAULT '{}',    -- JSON
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_glovo_store_hub_store_id ON glovo_store (hub_id, store_id);
CREATE INDEX        IF NOT EXISTS ix_glovo_store_hub_status   ON glovo_store (hub_id, glovo_status);
CREATE INDEX        IF NOT EXISTS ix_glovo_store_hub_active   ON glovo_store (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS idx_glovo_store_hub         ON glovo_store (hub_id, is_deleted);

-- Pedido de delivery entrante recibido de Glovo para una tienda.
-- order_code = id externo único de Glovo; order_number = correlativo GLO-YYYYMMDD-NNNN por hub.
-- items y delivery_address son JSON libre almacenados como TEXT.
CREATE TABLE IF NOT EXISTS glovo_order (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    store_id         TEXT NOT NULL,              -- FK -> glovo_store.id
    order_code       TEXT NOT NULL,              -- id externo de Glovo (idempotencia)
    order_number     TEXT NOT NULL,              -- GLO-YYYYMMDD-NNNN
    customer_name    TEXT NOT NULL DEFAULT '',
    customer_phone   TEXT NOT NULL DEFAULT '',
    total_amount     NUMERIC NOT NULL DEFAULT 0,
    currency         TEXT NOT NULL DEFAULT 'EUR',
    status           TEXT NOT NULL DEFAULT 'new', -- new|accepted|preparing|ready|delivered|cancelled
    created_at_glovo TEXT,                        -- timestamp original de Glovo (ISO o NULL)
    items            TEXT NOT NULL DEFAULT '[]',  -- JSON
    delivery_address TEXT NOT NULL DEFAULT '{}',  -- JSON
    notes            TEXT NOT NULL DEFAULT '',
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT,
    FOREIGN KEY (store_id) REFERENCES glovo_store (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_glovo_order_hub_order_code   ON glovo_order (hub_id, order_code);
CREATE UNIQUE INDEX IF NOT EXISTS ix_glovo_order_hub_order_number ON glovo_order (hub_id, order_number);
CREATE INDEX        IF NOT EXISTS ix_glovo_order_hub_status       ON glovo_order (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_glovo_order_hub_store        ON glovo_order (hub_id, store_id);
CREATE INDEX        IF NOT EXISTS ix_glovo_order_hub_created      ON glovo_order (hub_id, created_at_glovo);
CREATE INDEX        IF NOT EXISTS idx_glovo_order_hub             ON glovo_order (hub_id, is_deleted);

-- Auditoría de una operación de sincronización de menú/catálogo contra una tienda Glovo.
CREATE TABLE IF NOT EXISTS glovo_menu_sync (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    store_id     TEXT NOT NULL,                  -- FK -> glovo_store.id
    sync_type    TEXT NOT NULL DEFAULT 'full',   -- full|incremental
    started_at   TEXT NOT NULL,
    completed_at TEXT,
    status       TEXT NOT NULL DEFAULT 'running', -- running|completed|failed
    items_synced INTEGER NOT NULL DEFAULT 0,
    error_log    TEXT NOT NULL DEFAULT '',
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT,
    FOREIGN KEY (store_id) REFERENCES glovo_store (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_glovo_menu_sync_hub_store ON glovo_menu_sync (hub_id, store_id);
CREATE INDEX IF NOT EXISTS ix_glovo_menu_sync_hub_status ON glovo_menu_sync (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_glovo_menu_sync_started    ON glovo_menu_sync (started_at);
CREATE INDEX IF NOT EXISTS idx_glovo_menu_sync_hub       ON glovo_menu_sync (hub_id, is_deleted);

-- Mapeo entre un producto Glovo y la referencia de producto local del hub.
-- (store_id, glovo_product_id) único por hub (ix_glovo_product_hub_store_pid).
CREATE TABLE IF NOT EXISTS glovo_product (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    store_id          TEXT NOT NULL,             -- FK -> glovo_store.id
    glovo_product_id  TEXT NOT NULL,             -- id externo de Glovo
    local_product_ref TEXT NOT NULL DEFAULT '',  -- referencia al producto local (sin FK cruzada de tabla)
    name              TEXT NOT NULL,
    price             NUMERIC NOT NULL DEFAULT 0,
    is_available      INTEGER NOT NULL DEFAULT 1,
    last_synced_at    TEXT,
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    FOREIGN KEY (store_id) REFERENCES glovo_store (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_glovo_product_hub_store_pid ON glovo_product (hub_id, store_id, glovo_product_id);
CREATE INDEX        IF NOT EXISTS ix_glovo_product_hub_store     ON glovo_product (hub_id, store_id);
CREATE INDEX        IF NOT EXISTS ix_glovo_product_hub_local_ref ON glovo_product (hub_id, local_product_ref);
CREATE INDEX        IF NOT EXISTS ix_glovo_product_hub_avail     ON glovo_product (hub_id, is_available);
CREATE INDEX        IF NOT EXISTS idx_glovo_product_hub          ON glovo_product (hub_id, is_deleted);

-- Contador atómico por (hub, día) para generar order_number GLO-YYYYMMDD-NNNN.
-- El UPSERT atómico (incremento sin ventana SELECT->UPDATE) lo ejecuta el runtime/WASM;
-- ver WASM-TODO.md. Sin soft-delete: es infraestructura de secuencia, no entidad de negocio.
CREATE TABLE IF NOT EXISTS glovo_order_counter (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    day         TEXT NOT NULL,                   -- YYYYMMDD
    last_number INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_glovo_order_counter_hub_day ON glovo_order_counter (hub_id, day);
