-- Orders · esquema inicial (SQLite).
-- IMPORTANTE (contrato hub-next §2.3 cross-module + §2.5 fila estándar):
-- el módulo `orders` NO puede leer ni escribir la tabla privada de otro módulo
-- (p.ej. sales_sale). Por eso `orders` OWNea su propia tabla de gestión de pedidos
-- `orders_order` con los campos de gestión (canal, prioridad, datos de entrega,
-- fecha/hora solicitada, notas internas) + un `sale_id` OPCIONAL como mera
-- referencia a una venta de `sales`. Cualquier dato de la venta se obtiene por
-- `sale_id` vía contrato `sales.*` (query pública), nunca con SELECT directo.
-- Aquí viven:
--   - orders_order:    cabecera de gestión del pedido (tabla propia).
--   - orders_settings: configuración singleton por hub.
--   - orders_note:     bitácora de comunicación / cambios de estado por pedido.
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Pedido (cabecera de gestión, tabla PROPIA del módulo orders).
-- status ∈ ('draft','pending','completed','voided').
-- channel ∈ ('phone','whatsapp','email','in_person', ...).
-- priority ∈ ('low','normal','high','urgent').
-- sale_id: referencia OPCIONAL a una venta de `sales` (NULL hasta vincular).
CREATE TABLE IF NOT EXISTS orders_order (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    order_number     TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'draft',
    channel          TEXT NOT NULL DEFAULT 'phone',
    priority         TEXT NOT NULL DEFAULT 'normal',
    customer_id      TEXT,
    customer_name    TEXT NOT NULL DEFAULT '',
    customer_phone   TEXT NOT NULL DEFAULT '',
    delivery_address TEXT NOT NULL DEFAULT '',
    requested_date   TEXT,
    requested_time   TEXT,
    total            NUMERIC NOT NULL DEFAULT 0,
    notes            TEXT NOT NULL DEFAULT '',
    internal_notes   TEXT NOT NULL DEFAULT '',
    -- Referencia opcional a la venta de `sales` (sin FK cross-module: contrato, no import).
    sale_id          TEXT,
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT,
    updated_at       TEXT
);
CREATE INDEX IF NOT EXISTS ix_orders_order_hub_status  ON orders_order (hub_id, status, is_deleted);
CREATE INDEX IF NOT EXISTS ix_orders_order_hub_created ON orders_order (hub_id, created_at);
CREATE INDEX IF NOT EXISTS ix_orders_order_hub_sale    ON orders_order (hub_id, sale_id);

-- Configuración singleton por hub.
CREATE TABLE IF NOT EXISTS orders_settings (
    id                        TEXT PRIMARY KEY,
    hub_id                    TEXT NOT NULL,
    auto_confirm              INTEGER NOT NULL DEFAULT 0,
    require_customer          INTEGER NOT NULL DEFAULT 0,
    default_channel           TEXT    NOT NULL DEFAULT 'phone',
    notify_on_new_order       INTEGER NOT NULL DEFAULT 1,
    allow_partial_fulfillment INTEGER NOT NULL DEFAULT 0,
    is_deleted                INTEGER NOT NULL DEFAULT 0,
    deleted_at                TEXT,
    created_by                TEXT,
    updated_by                TEXT,
    created_at                TEXT,
    updated_at                TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_settings_hub ON orders_settings (hub_id);

-- Nota / entrada de bitácora de un pedido (referencia a orders_order por order_id).
-- note_type ∈ ('note','status_change','customer_contact','internal').
CREATE TABLE IF NOT EXISTS orders_note (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    order_id      TEXT NOT NULL,
    note_type     TEXT NOT NULL DEFAULT 'note',
    content       TEXT NOT NULL,
    author_id     TEXT,
    author_name   TEXT NOT NULL DEFAULT '',
    from_status   TEXT NOT NULL DEFAULT '',
    to_status     TEXT NOT NULL DEFAULT '',
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT,
    updated_at    TEXT
);
CREATE INDEX IF NOT EXISTS ix_orders_note_hub_order ON orders_note (hub_id, order_id, is_deleted);
