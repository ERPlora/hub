-- Purchase Orders · esquema inicial (SQLite). Portado fielmente de old_modules/m_purchase_orders/models.py.
-- Modelos: Supplier, PurchaseOrder, PurchaseOrderLine, PurchaseOrderCounter (número atómico).
-- Workflow del pedido: draft -> confirmed -> received  (\-> cancelled).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Proveedor / directorio de vendors.
CREATE TABLE IF NOT EXISTS purchase_orders_supplier (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    name        TEXT NOT NULL,
    tax_id      TEXT NOT NULL DEFAULT '',
    email       TEXT NOT NULL DEFAULT '',
    phone       TEXT NOT NULL DEFAULT '',
    address     TEXT NOT NULL DEFAULT '',
    notes       TEXT NOT NULL DEFAULT '',
    is_active   INTEGER NOT NULL DEFAULT 1,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT,
    updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS ix_po_supplier_hub_name   ON purchase_orders_supplier (hub_id, name);
CREATE INDEX IF NOT EXISTS ix_po_supplier_hub_active ON purchase_orders_supplier (hub_id, is_active);

-- Contador atómico de número de pedido por (hub, día). Upsert sin ventana de carrera.
CREATE TABLE IF NOT EXISTS purchase_orders_order_counter (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    day         TEXT NOT NULL,
    last_number INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_po_counter_hub_day ON purchase_orders_order_counter (hub_id, day);

-- Cabecera del pedido de compra (las líneas van en tabla aparte).
CREATE TABLE IF NOT EXISTS purchase_orders_order (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    supplier_id   TEXT NOT NULL,
    order_number  TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'draft',   -- draft|confirmed|received|cancelled
    order_date    TEXT NOT NULL,
    expected_date TEXT,
    total_amount  NUMERIC NOT NULL DEFAULT 0,
    notes         TEXT NOT NULL DEFAULT '',
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT,
    updated_at    TEXT,
    FOREIGN KEY (supplier_id) REFERENCES purchase_orders_supplier (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_po_order_hub_number   ON purchase_orders_order (hub_id, order_number);
CREATE INDEX        IF NOT EXISTS ix_po_order_hub_created  ON purchase_orders_order (hub_id, created_at);
CREATE INDEX        IF NOT EXISTS ix_po_order_hub_status   ON purchase_orders_order (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_po_order_hub_supplier ON purchase_orders_order (hub_id, supplier_id);

-- Línea de pedido (line_total = quantity * unit_price, calculado server-side).
CREATE TABLE IF NOT EXISTS purchase_orders_order_line (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    purchase_order_id TEXT NOT NULL,
    product_name      TEXT NOT NULL,
    quantity          NUMERIC NOT NULL DEFAULT 1,
    unit_price        NUMERIC NOT NULL,
    line_total        NUMERIC NOT NULL DEFAULT 0,
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT,
    updated_at        TEXT,
    FOREIGN KEY (purchase_order_id) REFERENCES purchase_orders_order (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_po_line_hub_order ON purchase_orders_order_line (hub_id, purchase_order_id);
