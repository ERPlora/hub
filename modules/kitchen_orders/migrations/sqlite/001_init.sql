-- Kitchen Orders · esquema inicial (SQLite). Portado de old_modules/m_commands/models.py.
-- Gestión de comandas de producción (cocinas, talleres, obradores, fábricas):
-- estaciones, comandas (Order), líneas (OrderItem), modificadores y enrutado
-- producto/categoría → estación. Tablas con prefijo 'kitchen_orders_'.
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Configuración por hub del módulo de comandas (una fila por hub).
CREATE TABLE IF NOT EXISTS kitchen_orders_settings (
    id                       TEXT PRIMARY KEY,
    hub_id                   TEXT NOT NULL,
    auto_print_tickets       INTEGER NOT NULL DEFAULT 1,
    show_prep_time           INTEGER NOT NULL DEFAULT 1,
    alert_threshold_minutes  INTEGER NOT NULL DEFAULT 15,
    use_rounds               INTEGER NOT NULL DEFAULT 1,
    auto_fire_on_round       INTEGER NOT NULL DEFAULT 0,
    default_order_type       TEXT NOT NULL DEFAULT 'dine_in',   -- dine_in|takeaway|delivery
    sound_on_new_order       INTEGER NOT NULL DEFAULT 1,
    is_deleted               INTEGER NOT NULL DEFAULT 0,
    deleted_at               TEXT,
    created_by               TEXT,
    updated_by               TEXT,
    created_at               TEXT NOT NULL,
    updated_at               TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_kitchen_orders_settings_hub ON kitchen_orders_settings (hub_id);
CREATE INDEX        IF NOT EXISTS idx_kitchen_orders_settings_hub ON kitchen_orders_settings (hub_id, is_deleted);

-- Estación de producción para enrutar las líneas de comanda (Bar, Plancha, Postres…).
-- name es único por hub.
CREATE TABLE IF NOT EXISTS kitchen_orders_station (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    name         TEXT NOT NULL,
    name_es      TEXT NOT NULL DEFAULT '',
    description  TEXT NOT NULL DEFAULT '',
    color        TEXT NOT NULL DEFAULT '#F97316',
    icon         TEXT NOT NULL DEFAULT 'flame-outline',
    printer_name TEXT NOT NULL DEFAULT '',
    sort_order   INTEGER NOT NULL DEFAULT 0,
    is_active    INTEGER NOT NULL DEFAULT 1,
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_kitchen_orders_station_hub_name ON kitchen_orders_station (hub_id, name);
CREATE INDEX        IF NOT EXISTS ix_kitchen_orders_station_hub_active ON kitchen_orders_station (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS idx_kitchen_orders_station_hub ON kitchen_orders_station (hub_id, is_deleted);

-- Comanda / ticket. Los enlaces a otras tablas (table_id, sale_id, customer_id) son
-- IDs de OTROS módulos (tables/sales/customers): se guardan como referencia opaca y
-- NUNCA se hace JOIN contra tablas privadas ajenas (cross-módulo = queries/eventos).
CREATE TABLE IF NOT EXISTS kitchen_orders_order (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    order_number TEXT NOT NULL,
    table_id     TEXT,                              -- ref a tables_table (otro módulo)
    sale_id      TEXT,                              -- ref a sales_sale (otro módulo)
    customer_id  TEXT,                              -- ref a customers_customer (otro módulo)
    waiter_id    TEXT,
    order_type   TEXT NOT NULL DEFAULT 'dine_in',   -- dine_in|takeaway|delivery
    status       TEXT NOT NULL DEFAULT 'pending',   -- pending|preparing|ready|served|paid|cancelled
    priority     TEXT NOT NULL DEFAULT 'normal',    -- normal|rush|vip
    round_number INTEGER NOT NULL DEFAULT 1,
    notes        TEXT NOT NULL DEFAULT '',
    subtotal     NUMERIC NOT NULL DEFAULT 0,
    tax          NUMERIC NOT NULL DEFAULT 0,
    discount     NUMERIC NOT NULL DEFAULT 0,
    total        NUMERIC NOT NULL DEFAULT 0,
    fired_at     TEXT,
    ready_at     TEXT,
    served_at    TEXT,
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT
);
CREATE INDEX IF NOT EXISTS ix_kitchen_orders_order_hub_status  ON kitchen_orders_order (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_kitchen_orders_order_hub_created ON kitchen_orders_order (hub_id, created_at);
CREATE INDEX IF NOT EXISTS ix_kitchen_orders_order_hub_type    ON kitchen_orders_order (hub_id, order_type);
CREATE INDEX IF NOT EXISTS ix_kitchen_orders_order_hub_number  ON kitchen_orders_order (hub_id, order_number);
CREATE INDEX IF NOT EXISTS idx_kitchen_orders_order_hub        ON kitchen_orders_order (hub_id, is_deleted);

-- Línea de comanda enrutada a una estación. product_id es ref opaca a inventory.
CREATE TABLE IF NOT EXISTS kitchen_orders_order_item (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    order_id     TEXT NOT NULL,
    station_id   TEXT,
    product_id   TEXT,                              -- ref a inventory (otro módulo)
    product_name TEXT NOT NULL,
    unit_price   NUMERIC NOT NULL DEFAULT 0,
    quantity     INTEGER NOT NULL DEFAULT 1,
    total        NUMERIC NOT NULL DEFAULT 0,
    modifiers    TEXT NOT NULL DEFAULT '',
    notes        TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'pending',   -- pending|preparing|ready|served|cancelled
    seat_number  INTEGER,
    fired_at     TEXT,
    started_at   TEXT,
    completed_at TEXT,
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT,
    FOREIGN KEY (order_id)   REFERENCES kitchen_orders_order (id)   ON DELETE CASCADE,
    FOREIGN KEY (station_id) REFERENCES kitchen_orders_station (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_kitchen_orders_item_status         ON kitchen_orders_order_item (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_kitchen_orders_item_station_status ON kitchen_orders_order_item (hub_id, station_id, status);
CREATE INDEX IF NOT EXISTS ix_kitchen_orders_item_order          ON kitchen_orders_order_item (hub_id, order_id);
CREATE INDEX IF NOT EXISTS idx_kitchen_orders_order_item_hub     ON kitchen_orders_order_item (hub_id, is_deleted);

-- Modificador aplicado a una línea (extra de ingrediente, punto de cocción…).
CREATE TABLE IF NOT EXISTS kitchen_orders_order_modifier (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    order_item_id TEXT NOT NULL,
    name          TEXT NOT NULL,
    price         NUMERIC NOT NULL DEFAULT 0,
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT,
    FOREIGN KEY (order_item_id) REFERENCES kitchen_orders_order_item (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_kitchen_orders_modifier_item ON kitchen_orders_order_modifier (hub_id, order_item_id);
CREATE INDEX IF NOT EXISTS idx_kitchen_orders_order_modifier_hub ON kitchen_orders_order_modifier (hub_id, is_deleted);

-- Enrutado producto → estación (mapeo directo). product_id es ref opaca a inventory.
CREATE TABLE IF NOT EXISTS kitchen_orders_product_station (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    product_id  TEXT NOT NULL,                      -- ref a inventory (otro módulo)
    station_id  TEXT NOT NULL,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT,
    FOREIGN KEY (station_id) REFERENCES kitchen_orders_station (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_kitchen_orders_product_station_hub_product ON kitchen_orders_product_station (hub_id, product_id);
CREATE INDEX        IF NOT EXISTS idx_kitchen_orders_product_station_hub ON kitchen_orders_product_station (hub_id, is_deleted);

-- Enrutado categoría → estación. category_id es ref opaca a inventory.
CREATE TABLE IF NOT EXISTS kitchen_orders_category_station (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    category_id TEXT NOT NULL,                      -- ref a inventory (otro módulo)
    station_id  TEXT NOT NULL,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT,
    FOREIGN KEY (station_id) REFERENCES kitchen_orders_station (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_kitchen_orders_category_station_hub_category ON kitchen_orders_category_station (hub_id, category_id);
CREATE INDEX        IF NOT EXISTS idx_kitchen_orders_category_station_hub ON kitchen_orders_category_station (hub_id, is_deleted);
