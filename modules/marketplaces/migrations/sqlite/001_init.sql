-- Marketplaces · esquema inicial (SQLite). Portado fielmente de old_modules/m_marketplaces/models.py.
-- Conectores a marketplaces externos (Amazon, eBay, AliExpress, Etsy, ...).
-- Modelos: MarketplaceConnection (credenciales + estado por cuenta externa),
-- MarketplaceProductMapping (producto local ↔ listing externo), MarketplaceOrder
-- (pedido importado), SyncRun (registro de una ejecución de sync) y
-- MarketplaceOrderCounter (secuencia atómica por hub+día para order_number).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Conexión a una cuenta de marketplace externo.
-- code es único por hub. credentials guarda claves/tokens (la UI/serializador DEBE
-- enmascararlos antes de devolverlos al cliente — ver WASM-TODO). settings es JSON libre.
CREATE TABLE IF NOT EXISTS marketplaces_connection (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    code             TEXT NOT NULL,
    platform         TEXT NOT NULL DEFAULT 'other',   -- amazon|ebay|aliexpress|etsy|other
    name             TEXT NOT NULL,
    is_active        INTEGER NOT NULL DEFAULT 1,
    credentials      TEXT NOT NULL DEFAULT '{}',       -- JSON: API key/secret/OAuth tokens
    region           TEXT NOT NULL DEFAULT '',
    last_sync_at     TEXT,                             -- ISO timestamp o NULL
    last_sync_status TEXT NOT NULL DEFAULT '',
    settings         TEXT NOT NULL DEFAULT '{}',       -- JSON libre de configuración
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_mp_connection_hub_code     ON marketplaces_connection (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_mp_connection_hub_platform ON marketplaces_connection (hub_id, platform);
CREATE INDEX        IF NOT EXISTS ix_mp_connection_hub_active   ON marketplaces_connection (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS idx_marketplaces_connection_hub ON marketplaces_connection (hub_id, is_deleted);

-- Mapeo entre un producto local y un listing del marketplace externo.
-- local_product_ref es la referencia opaca al catálogo local (no es FK directa: el
-- catálogo lo OWNea otro módulo; cross-módulo via contrato, no FK).
CREATE TABLE IF NOT EXISTS marketplaces_product_mapping (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    connection_id       TEXT NOT NULL,
    local_product_ref   TEXT NOT NULL,
    external_product_id TEXT NOT NULL,
    external_sku        TEXT NOT NULL DEFAULT '',
    sync_enabled        INTEGER NOT NULL DEFAULT 1,
    last_synced_at      TEXT,
    sync_status         TEXT NOT NULL DEFAULT 'pending',  -- synced|error|pending
    error_message       TEXT NOT NULL DEFAULT '',
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT,
    FOREIGN KEY (connection_id) REFERENCES marketplaces_connection (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_mp_mapping_hub_connection ON marketplaces_product_mapping (hub_id, connection_id);
CREATE INDEX IF NOT EXISTS ix_mp_mapping_hub_local_ref  ON marketplaces_product_mapping (hub_id, local_product_ref);
CREATE INDEX IF NOT EXISTS ix_mp_mapping_hub_status     ON marketplaces_product_mapping (hub_id, sync_status);
CREATE INDEX IF NOT EXISTS idx_marketplaces_product_mapping_hub ON marketplaces_product_mapping (hub_id, is_deleted);

-- Pedido importado desde un marketplace externo.
-- order_number es único por hub (MP-YYYYMMDD-NNNN, generado atómico — ver WASM-TODO).
-- (connection_id, external_order_id) único garantiza idempotencia de import.
CREATE TABLE IF NOT EXISTS marketplaces_order (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    connection_id     TEXT NOT NULL,
    external_order_id TEXT NOT NULL,
    order_number      TEXT NOT NULL,
    customer_name     TEXT NOT NULL,
    customer_email    TEXT NOT NULL DEFAULT '',
    total_amount      NUMERIC NOT NULL DEFAULT 0,
    currency          TEXT NOT NULL DEFAULT 'EUR',
    order_date        TEXT,                              -- ISO timestamp o NULL
    status            TEXT NOT NULL DEFAULT 'new',       -- new|imported|fulfilled|cancelled
    shipping_address  TEXT NOT NULL DEFAULT '{}',        -- JSON
    items             TEXT NOT NULL DEFAULT '[]',        -- JSON: lista de líneas
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    FOREIGN KEY (connection_id) REFERENCES marketplaces_connection (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_mp_order_connection_external ON marketplaces_order (connection_id, external_order_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_mp_order_hub_number          ON marketplaces_order (hub_id, order_number);
CREATE INDEX        IF NOT EXISTS ix_mp_order_hub_status          ON marketplaces_order (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_mp_order_hub_date            ON marketplaces_order (hub_id, order_date);
CREATE INDEX        IF NOT EXISTS idx_marketplaces_order_hub      ON marketplaces_order (hub_id, is_deleted);

-- Registro de una ejecución de sync contra una conexión.
CREATE TABLE IF NOT EXISTS marketplaces_sync_run (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    connection_id TEXT NOT NULL,
    sync_type     TEXT NOT NULL DEFAULT 'products',  -- products|orders|inventory|prices
    started_at    TEXT NOT NULL,                     -- ISO timestamp
    completed_at  TEXT,
    status        TEXT NOT NULL DEFAULT 'running',   -- running|completed|failed
    items_synced  INTEGER NOT NULL DEFAULT 0,
    items_failed  INTEGER NOT NULL DEFAULT 0,
    error_log     TEXT NOT NULL DEFAULT '',
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT,
    FOREIGN KEY (connection_id) REFERENCES marketplaces_connection (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_mp_sync_hub_connection ON marketplaces_sync_run (hub_id, connection_id);
CREATE INDEX IF NOT EXISTS ix_mp_sync_hub_status     ON marketplaces_sync_run (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_mp_sync_hub_type       ON marketplaces_sync_run (hub_id, sync_type);
CREATE INDEX IF NOT EXISTS idx_marketplaces_sync_run_hub ON marketplaces_sync_run (hub_id, is_deleted);

-- Contador atómico por (hub, día) para order_number. Se escribe via UPSERT
-- (INSERT ... ON CONFLICT DO UPDATE ... RETURNING) — incremento en una sola ida y
-- vuelta, sin carrera SELECT→UPDATE. Lo invoca el handler WASM de import (ver WASM-TODO).
CREATE TABLE IF NOT EXISTS marketplaces_order_counter (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    day         TEXT NOT NULL,                  -- YYYYMMDD
    last_number INTEGER NOT NULL DEFAULT 0,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_mp_order_counter_hub_day ON marketplaces_order_counter (hub_id, day);
CREATE INDEX        IF NOT EXISTS idx_marketplaces_order_counter_hub ON marketplaces_order_counter (hub_id, is_deleted);
