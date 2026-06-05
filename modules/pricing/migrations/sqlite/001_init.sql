-- Pricing · esquema inicial (SQLite). Portado fielmente de old_modules/m_pricing/models.py.
-- Modelos: PriceList, PriceListItem, DiscountRule.
-- Listas de precios con scope por divisa/segmento + items por producto y bracket
-- de cantidad; reglas de descuento evaluadas por prioridad sobre un importe.
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Lista de precios (scope por hub, opcionalmente por segmento).
CREATE TABLE IF NOT EXISTS pricing_price_list (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    code         TEXT NOT NULL,
    name         TEXT NOT NULL,
    currency     TEXT NOT NULL DEFAULT 'EUR',
    is_default   INTEGER NOT NULL DEFAULT 0,
    is_active    INTEGER NOT NULL DEFAULT 1,
    valid_from   TEXT,                        -- ISO YYYY-MM-DD
    valid_until  TEXT,                        -- ISO YYYY-MM-DD
    segment      TEXT,                        -- NULL = cualquier segmento; si no: customer|business|wholesale|retail
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT,
    updated_at   TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pricing_list_hub_code     ON pricing_price_list (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_pricing_list_hub_active   ON pricing_price_list (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS ix_pricing_list_hub_segment  ON pricing_price_list (hub_id, segment);
CREATE INDEX        IF NOT EXISTS idx_pricing_price_list_hub   ON pricing_price_list (hub_id, is_deleted);

-- Item de lista de precios (precio por producto y bracket de cantidad).
CREATE TABLE IF NOT EXISTS pricing_price_list_item (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    price_list_id TEXT NOT NULL,
    product_ref   TEXT NOT NULL,
    price         NUMERIC NOT NULL DEFAULT 0,
    min_quantity  NUMERIC NOT NULL DEFAULT 1,
    max_quantity  NUMERIC,
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT,
    updated_at    TEXT,
    FOREIGN KEY (price_list_id) REFERENCES pricing_price_list (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_pricing_item_hub_list_product ON pricing_price_list_item (hub_id, price_list_id, product_ref);
CREATE INDEX IF NOT EXISTS idx_pricing_price_list_item_hub  ON pricing_price_list_item (hub_id, is_deleted);

-- Regla de descuento (aplicada sobre un importe; evaluada por prioridad).
CREATE TABLE IF NOT EXISTS pricing_discount_rule (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    code         TEXT NOT NULL,
    name         TEXT NOT NULL,
    rule_type    TEXT NOT NULL DEFAULT 'percent',   -- percent|fixed|buy_x_get_y|tiered
    value        NUMERIC NOT NULL DEFAULT 0,
    min_amount   NUMERIC,
    max_amount   NUMERIC,
    applies_to   TEXT NOT NULL DEFAULT 'all',        -- all|customer_segment|product_category
    conditions   TEXT NOT NULL DEFAULT '{}',         -- JSON libre (tiers, buy/get, segment…)
    valid_from   TEXT,                               -- ISO YYYY-MM-DD
    valid_until  TEXT,                               -- ISO YYYY-MM-DD
    is_active    INTEGER NOT NULL DEFAULT 1,
    priority     INTEGER NOT NULL DEFAULT 100,        -- menor = se aplica antes
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT,
    updated_at   TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pricing_rule_hub_code            ON pricing_discount_rule (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_pricing_rule_hub_active_priority ON pricing_discount_rule (hub_id, is_active, priority);
CREATE INDEX        IF NOT EXISTS idx_pricing_discount_rule_hub       ON pricing_discount_rule (hub_id, is_deleted);
