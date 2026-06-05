-- Delivery · esquema inicial (SQLite). Portado fielmente de old_modules/m_delivery/models.py.
-- Modelos: DeliverySettings (singleton por hub), DeliveryZone (zona geográfica con tarifa),
-- Driver (repartidor), DeliveryOrder (pedido takeaway/delivery) y DeliveryOrderItem (línea).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Ajustes de delivery, uno por hub (UNIQUE hub_id). Tiempo de preparación por defecto
-- y si se auto-asigna zona por código postal.
CREATE TABLE IF NOT EXISTS delivery_settings (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    default_prep_time INTEGER NOT NULL DEFAULT 20,
    auto_assign_zone  INTEGER NOT NULL DEFAULT 1,
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_delivery_settings_hub ON delivery_settings (hub_id);
CREATE INDEX        IF NOT EXISTS idx_delivery_settings_hub ON delivery_settings (hub_id, is_deleted);

-- Zona de reparto: nombre, pedido mínimo, tarifa, tiempo estimado, radio máximo y
-- lista de códigos postales (JSON). sort_order para ordenar en la UI.
CREATE TABLE IF NOT EXISTS delivery_zone (
    id             TEXT PRIMARY KEY,
    hub_id         TEXT NOT NULL,
    name           TEXT NOT NULL,
    min_order      NUMERIC NOT NULL DEFAULT 0,
    delivery_fee   NUMERIC NOT NULL DEFAULT 0,
    estimated_time INTEGER NOT NULL DEFAULT 30,
    is_active      INTEGER NOT NULL DEFAULT 1,
    zip_codes      TEXT NOT NULL DEFAULT '[]',   -- JSON array de códigos postales
    max_radius_km  NUMERIC,                       -- NULL = sin límite de radio
    sort_order     INTEGER NOT NULL DEFAULT 0,
    is_deleted     INTEGER NOT NULL DEFAULT 0,
    deleted_at     TEXT,
    created_by     TEXT,
    updated_by     TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT
);
CREATE INDEX IF NOT EXISTS ix_delivery_zone_hub_active ON delivery_zone (hub_id, is_active);
CREATE INDEX IF NOT EXISTS idx_delivery_zone_hub       ON delivery_zone (hub_id, is_deleted);

-- Repartidor: nombre, teléfono, tipo de vehículo, si es externo (subcontratado) y notas.
CREATE TABLE IF NOT EXISTS delivery_driver (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    name         TEXT NOT NULL,
    phone        TEXT NOT NULL,
    is_active    INTEGER NOT NULL DEFAULT 1,
    vehicle_type TEXT NOT NULL DEFAULT '',
    is_external  INTEGER NOT NULL DEFAULT 0,
    notes        TEXT NOT NULL DEFAULT '',
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT
);
CREATE INDEX IF NOT EXISTS ix_delivery_driver_hub_active ON delivery_driver (hub_id, is_active);
CREATE INDEX IF NOT EXISTS idx_delivery_driver_hub       ON delivery_driver (hub_id, is_deleted);

-- Pedido de reparto o recogida. number es único por hub (formato DEL-NNNN, generado en
-- runtime/WASM de forma atómica). sale_id es una referencia laxa (UUID, sin FK) al Sale
-- originante en el módulo sales. customer_name/phone/delivery_address quedan como
-- retro-compat (la fuente real es el Sale vinculado). Totales recalculados desde las líneas.
CREATE TABLE IF NOT EXISTS delivery_order (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    number           TEXT NOT NULL,
    order_type       TEXT NOT NULL DEFAULT 'delivery',  -- takeaway|delivery
    customer_name    TEXT NOT NULL,                      -- DEPRECATED: usar sales.Sale.customer
    customer_phone   TEXT NOT NULL,                      -- DEPRECATED: usar sales.Sale.customer
    delivery_address TEXT NOT NULL DEFAULT '',           -- DEPRECATED: usar sales.Sale.delivery_address
    sale_id          TEXT,                               -- referencia laxa a sales.Sale (sin FK)
    delivery_zone_id TEXT,                               -- FK lógica a delivery_zone (SET NULL)
    driver_id        TEXT,                               -- FK lógica a delivery_driver (SET NULL)
    status           TEXT NOT NULL DEFAULT 'pending',    -- pending|preparing|ready|in_transit|delivered|picked_up|cancelled
    ordered_at       TEXT NOT NULL,
    promised_at      TEXT,
    completed_at     TEXT,
    subtotal         NUMERIC NOT NULL DEFAULT 0,
    delivery_fee     NUMERIC NOT NULL DEFAULT 0,
    total            NUMERIC NOT NULL DEFAULT 0,
    payment_method   TEXT NOT NULL DEFAULT '',
    paid             INTEGER NOT NULL DEFAULT 0,
    notes            TEXT NOT NULL DEFAULT '',
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT,
    FOREIGN KEY (delivery_zone_id) REFERENCES delivery_zone (id) ON DELETE SET NULL,
    FOREIGN KEY (driver_id)        REFERENCES delivery_driver (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_delivery_order_hub_number  ON delivery_order (hub_id, number);
CREATE INDEX        IF NOT EXISTS ix_delivery_order_hub_status  ON delivery_order (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_delivery_order_hub_created ON delivery_order (hub_id, created_at);
CREATE INDEX        IF NOT EXISTS ix_delivery_order_sale        ON delivery_order (hub_id, sale_id);
CREATE INDEX        IF NOT EXISTS idx_delivery_order_hub        ON delivery_order (hub_id, is_deleted);

-- Línea de pedido: producto, cantidad, precio unitario y notas. line_total = quantity * unit_price
-- se calcula en runtime/WASM (no se persiste de forma derivada salvo en totales del pedido).
CREATE TABLE IF NOT EXISTS delivery_order_item (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    order_id     TEXT NOT NULL,
    product_name TEXT NOT NULL,
    quantity     INTEGER NOT NULL DEFAULT 1,
    unit_price   NUMERIC NOT NULL DEFAULT 0,
    notes        TEXT NOT NULL DEFAULT '',
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT,
    FOREIGN KEY (order_id) REFERENCES delivery_order (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_delivery_order_item_order ON delivery_order_item (hub_id, order_id);
CREATE INDEX IF NOT EXISTS idx_delivery_order_item_hub  ON delivery_order_item (hub_id, is_deleted);
