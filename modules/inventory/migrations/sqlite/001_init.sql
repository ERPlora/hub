-- Inventory · esquema inicial (SQLite). Portado fielmente de modules/m_inventory/models.py.
-- Modelos: InventoryConfig (singleton), Category, Product, ProductVariant + M2M product↔category.
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Config singleton por hub.
CREATE TABLE IF NOT EXISTS inventory_config (
    id                      TEXT PRIMARY KEY,
    hub_id                  TEXT NOT NULL,
    allow_negative_stock    INTEGER NOT NULL DEFAULT 0,
    low_stock_alert_enabled INTEGER NOT NULL DEFAULT 1,
    auto_generate_sku       INTEGER NOT NULL DEFAULT 1,
    barcode_enabled         INTEGER NOT NULL DEFAULT 1,
    is_deleted              INTEGER NOT NULL DEFAULT 0,
    deleted_at              TEXT,
    created_by              TEXT,
    updated_by              TEXT,
    created_at              TEXT,
    updated_at              TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_inventory_config_hub ON inventory_config (hub_id);

-- Categoría.
CREATE TABLE IF NOT EXISTS inventory_category (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    name          TEXT NOT NULL,
    slug          TEXT NOT NULL DEFAULT '',
    icon          TEXT NOT NULL DEFAULT 'cube-outline',
    color         TEXT NOT NULL DEFAULT '#3880ff',
    image         TEXT NOT NULL DEFAULT '',
    description   TEXT NOT NULL DEFAULT '',
    "order"       INTEGER NOT NULL DEFAULT 0,
    tax_class_id  TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1,
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT,
    updated_at    TEXT
);
CREATE INDEX IF NOT EXISTS ix_inventory_category_order  ON inventory_category (hub_id, "order");
CREATE INDEX IF NOT EXISTS ix_inventory_category_active ON inventory_category (hub_id, is_active);

-- Producto.
CREATE TABLE IF NOT EXISTS inventory_product (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    name                TEXT NOT NULL,
    sku                 TEXT NOT NULL,
    ean13               TEXT,
    description         TEXT NOT NULL DEFAULT '',
    product_type        TEXT NOT NULL DEFAULT 'physical',   -- physical|service
    price               NUMERIC NOT NULL,
    cost                NUMERIC NOT NULL DEFAULT 0,
    stock               INTEGER NOT NULL DEFAULT 0,
    low_stock_threshold INTEGER NOT NULL DEFAULT 10,
    tax_class_id        TEXT,
    image               TEXT NOT NULL DEFAULT '',
    is_active           INTEGER NOT NULL DEFAULT 1,
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT,
    updated_at          TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_inventory_product_sku    ON inventory_product (hub_id, sku);
CREATE INDEX        IF NOT EXISTS ix_inventory_product_name   ON inventory_product (hub_id, name);
CREATE UNIQUE INDEX IF NOT EXISTS ix_inventory_product_ean13  ON inventory_product (hub_id, ean13);
CREATE INDEX        IF NOT EXISTS ix_inventory_product_active ON inventory_product (hub_id, is_active);

-- Variante de producto (stock independiente).
CREATE TABLE IF NOT EXISTS inventory_product_variant (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    product_id  TEXT NOT NULL,
    name        TEXT NOT NULL,
    sku         TEXT NOT NULL,
    attributes  TEXT NOT NULL DEFAULT '{}',
    price       NUMERIC NOT NULL,
    stock       INTEGER NOT NULL DEFAULT 0,
    image       TEXT NOT NULL DEFAULT '',
    is_active   INTEGER NOT NULL DEFAULT 1,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT,
    updated_at  TEXT,
    FOREIGN KEY (product_id) REFERENCES inventory_product (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_inventory_variant_product_name  ON inventory_product_variant (hub_id, product_id, name);
CREATE UNIQUE INDEX IF NOT EXISTS ix_inventory_variant_sku            ON inventory_product_variant (hub_id, sku);
CREATE INDEX        IF NOT EXISTS ix_inventory_variant_product_active ON inventory_product_variant (hub_id, product_id, is_active);

-- M2M producto ↔ categoría.
CREATE TABLE IF NOT EXISTS inventory_product_categories (
    product_id  TEXT NOT NULL,
    category_id TEXT NOT NULL,
    PRIMARY KEY (product_id, category_id),
    FOREIGN KEY (product_id)  REFERENCES inventory_product (id)  ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES inventory_category (id) ON DELETE CASCADE
);
