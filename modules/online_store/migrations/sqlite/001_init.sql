-- Online Store · esquema inicial (SQLite). Portado fielmente de old_modules/m_online_store/models.py.
-- Modelos: StoreConfig (singleton por hub), StoreCategory (taxonomía self-referential),
-- StoreProduct (ficha publicada en el escaparate) y StorePage (CMS).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Configuración del escaparate (singleton por hub: el runtime/UI garantiza una sola fila viva).
CREATE TABLE IF NOT EXISTS online_store_config (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    store_name       TEXT NOT NULL DEFAULT '',
    domain           TEXT NOT NULL DEFAULT '',
    default_currency TEXT NOT NULL DEFAULT 'EUR',
    language         TEXT NOT NULL DEFAULT 'es',
    is_published     INTEGER NOT NULL DEFAULT 0,
    theme            TEXT NOT NULL DEFAULT 'default',
    primary_color    TEXT NOT NULL DEFAULT '',
    logo_url         TEXT NOT NULL DEFAULT '',
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_online_store_config_hub ON online_store_config (hub_id, is_deleted);

-- Categoría jerárquica del escaparate (slug único por hub, parent_id self-referential).
CREATE TABLE IF NOT EXISTS online_store_category (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    slug         TEXT NOT NULL,
    name         TEXT NOT NULL,
    parent_id    TEXT,
    description  TEXT NOT NULL DEFAULT '',
    is_published INTEGER NOT NULL DEFAULT 0,
    "order"      INTEGER NOT NULL DEFAULT 0,
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT,
    FOREIGN KEY (parent_id) REFERENCES online_store_category (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_online_store_category_hub_slug      ON online_store_category (hub_id, slug);
CREATE INDEX        IF NOT EXISTS ix_online_store_category_hub_parent    ON online_store_category (hub_id, parent_id);
CREATE INDEX        IF NOT EXISTS ix_online_store_category_hub_published ON online_store_category (hub_id, is_published);
CREATE INDEX        IF NOT EXISTS idx_online_store_category_hub          ON online_store_category (hub_id, is_deleted);

-- Ficha de producto publicada en el escaparate (slug único por hub).
-- product_ref es un enlace laxo (texto libre, sin FK) al catálogo interno (inventory).
-- images es JSON portable (Postgres JSONB-equivalente; SQLite texto JSON).
CREATE TABLE IF NOT EXISTS online_store_product (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    product_ref       TEXT NOT NULL DEFAULT '',
    slug              TEXT NOT NULL,
    name              TEXT NOT NULL,
    description       TEXT NOT NULL DEFAULT '',
    short_description  TEXT NOT NULL DEFAULT '',
    price             NUMERIC NOT NULL DEFAULT 0,
    sale_price        NUMERIC,
    stock_quantity    INTEGER NOT NULL DEFAULT 0,
    sku               TEXT NOT NULL DEFAULT '',
    images            TEXT NOT NULL DEFAULT '[]',
    is_published      INTEGER NOT NULL DEFAULT 0,
    seo_title         TEXT NOT NULL DEFAULT '',
    seo_description   TEXT NOT NULL DEFAULT '',
    weight            NUMERIC,
    dimensions        TEXT NOT NULL DEFAULT '',
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_online_store_product_hub_slug      ON online_store_product (hub_id, slug);
CREATE INDEX        IF NOT EXISTS ix_online_store_product_hub_published ON online_store_product (hub_id, is_published);
CREATE INDEX        IF NOT EXISTS ix_online_store_product_hub_sku       ON online_store_product (hub_id, sku);
CREATE INDEX        IF NOT EXISTS idx_online_store_product_hub          ON online_store_product (hub_id, is_deleted);

-- Página CMS estática del escaparate (slug único por hub).
CREATE TABLE IF NOT EXISTS online_store_page (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    slug          TEXT NOT NULL,
    title         TEXT NOT NULL,
    content_html  TEXT NOT NULL DEFAULT '',
    is_published  INTEGER NOT NULL DEFAULT 0,
    order_in_menu INTEGER NOT NULL DEFAULT 0,
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_online_store_page_hub_slug      ON online_store_page (hub_id, slug);
CREATE INDEX        IF NOT EXISTS ix_online_store_page_hub_published ON online_store_page (hub_id, is_published);
CREATE INDEX        IF NOT EXISTS idx_online_store_page_hub          ON online_store_page (hub_id, is_deleted);
