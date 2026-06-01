-- Sales · esquema inicial (SQLite). Portado fielmente de old_modules/m_sales/models.py (v2.4.9).
-- Modelos: SalesSettings, SalesPaymentMethod, Sale, SaleItem (líneas), SaleCounter (número atómico),
-- ActiveCart, ParkedTicket. Contrato de fila §2.5: hub_id + soft-delete + auditoría.

-- Ajustes de ventas (singleton por hub).
CREATE TABLE IF NOT EXISTS sales_settings (
    id                   TEXT PRIMARY KEY,
    hub_id               TEXT NOT NULL,
    allow_cash           INTEGER NOT NULL DEFAULT 1,
    allow_card           INTEGER NOT NULL DEFAULT 1,
    allow_transfer       INTEGER NOT NULL DEFAULT 0,
    sync_products        INTEGER NOT NULL DEFAULT 1,
    sync_services        INTEGER NOT NULL DEFAULT 0,
    require_customer     INTEGER NOT NULL DEFAULT 0,
    allow_discounts      INTEGER NOT NULL DEFAULT 1,
    enable_parked_tickets INTEGER NOT NULL DEFAULT 1,
    default_tax_included INTEGER NOT NULL DEFAULT 1,
    ticket_expiry_hours  INTEGER NOT NULL DEFAULT 24,
    receipt_header       TEXT NOT NULL DEFAULT '',
    receipt_footer       TEXT NOT NULL DEFAULT '',
    receipt_footer_image TEXT NOT NULL DEFAULT '',
    is_deleted INTEGER NOT NULL DEFAULT 0, deleted_at TEXT,
    created_by TEXT, updated_by TEXT, created_at TEXT, updated_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_settings_hub ON sales_settings (hub_id);

-- Métodos de pago.
CREATE TABLE IF NOT EXISTS sales_payment_method (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    name              TEXT NOT NULL,
    type              TEXT NOT NULL DEFAULT 'cash',   -- cash|card|transfer|other
    icon              TEXT NOT NULL DEFAULT '',
    is_active         INTEGER NOT NULL DEFAULT 1,
    sort_order        INTEGER NOT NULL DEFAULT 0,
    opens_cash_drawer INTEGER NOT NULL DEFAULT 0,
    requires_change   INTEGER NOT NULL DEFAULT 0,
    is_deleted INTEGER NOT NULL DEFAULT 0, deleted_at TEXT,
    created_by TEXT, updated_by TEXT, created_at TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_payment_method_hub ON sales_payment_method (hub_id, is_deleted);

-- Contador atómico por hub y día → número de venta YYYYMMDD-NNNN.
CREATE TABLE IF NOT EXISTS sales_sale_counter (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    day         TEXT NOT NULL,
    last_number INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sale_counter ON sales_sale_counter (hub_id, day);

-- Venta (cabecera fiscal).
CREATE TABLE IF NOT EXISTS sales_sale (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    sale_number         TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'completed',  -- draft|pending|completed|voided|refunded
    subtotal            NUMERIC NOT NULL DEFAULT 0,
    tax_amount          NUMERIC NOT NULL DEFAULT 0,
    tax_breakdown       TEXT NOT NULL DEFAULT '{}',
    discount_amount     NUMERIC NOT NULL DEFAULT 0,
    discount_percent    NUMERIC NOT NULL DEFAULT 0,
    total               NUMERIC NOT NULL DEFAULT 0,
    payment_method_id   TEXT,
    payment_method_name TEXT NOT NULL DEFAULT '',
    amount_tendered     NUMERIC NOT NULL DEFAULT 0,
    change_due          NUMERIC NOT NULL DEFAULT 0,
    customer_id         TEXT,
    customer_name       TEXT NOT NULL DEFAULT '',
    employee_id         TEXT,
    notes               TEXT NOT NULL DEFAULT '',
    source_module       TEXT NOT NULL DEFAULT '',
    channel             TEXT NOT NULL DEFAULT '',
    table_id            TEXT,
    cash_session_id     TEXT,
    is_deleted INTEGER NOT NULL DEFAULT 0, deleted_at TEXT,
    created_by TEXT, updated_by TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sale_number     ON sales_sale (hub_id, sale_number);
CREATE INDEX        IF NOT EXISTS ix_sale_hub_created ON sales_sale (hub_id, created_at);
CREATE INDEX        IF NOT EXISTS ix_sale_hub_status  ON sales_sale (hub_id, status);

-- Línea de venta (hija de sale, IVA por línea).
CREATE TABLE IF NOT EXISTS sales_sale_item (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    sale_id          TEXT NOT NULL,
    product_id       TEXT,
    product_name     TEXT NOT NULL,
    product_sku      TEXT NOT NULL DEFAULT '',
    is_service       INTEGER NOT NULL DEFAULT 0,
    quantity         NUMERIC NOT NULL DEFAULT 1,
    unit_price       NUMERIC NOT NULL DEFAULT 0,
    discount_percent NUMERIC NOT NULL DEFAULT 0,
    tax_rate         NUMERIC NOT NULL DEFAULT 0,
    tax_class_name   TEXT NOT NULL DEFAULT '',
    net_amount       NUMERIC NOT NULL DEFAULT 0,
    tax_amount       NUMERIC NOT NULL DEFAULT 0,
    line_total       NUMERIC NOT NULL DEFAULT 0,
    modifiers        TEXT NOT NULL DEFAULT '{}',
    notes            TEXT NOT NULL DEFAULT '',
    created_at       TEXT,
    FOREIGN KEY (sale_id) REFERENCES sales_sale (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_sale_item_sale ON sales_sale_item (hub_id, sale_id);

-- Carrito activo persistido por empleado.
CREATE TABLE IF NOT EXISTS sales_active_cart (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    cart_data   TEXT NOT NULL DEFAULT '{}',
    is_deleted INTEGER NOT NULL DEFAULT 0, deleted_at TEXT,
    created_by TEXT, updated_by TEXT, created_at TEXT, updated_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_cart ON sales_active_cart (hub_id, employee_id);

-- Ticket aparcado.
CREATE TABLE IF NOT EXISTS sales_parked_ticket (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    ticket_number TEXT NOT NULL,
    cart_data     TEXT NOT NULL,
    employee_id   TEXT,
    notes         TEXT NOT NULL DEFAULT '',
    expires_at    TEXT,
    is_deleted INTEGER NOT NULL DEFAULT 0, deleted_at TEXT,
    created_by TEXT, updated_by TEXT, created_at TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_parked_created ON sales_parked_ticket (hub_id, created_at);
CREATE INDEX IF NOT EXISTS ix_parked_expires ON sales_parked_ticket (hub_id, expires_at);
