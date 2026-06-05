-- Supplier Invoices · esquema inicial (SQLite). Portado fielmente de modules/m_supplier_invoices/models.py.
-- Modelos: SupplierInvoice (cabecera, ciclo pending→validated→paid|cancelled) + SupplierInvoiceLine (líneas).
-- Facturas RECIBIDAS de proveedores (entrantes), distintas del módulo fiscal `invoice` (emitidas por el hub).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Cabecera de factura de proveedor.
CREATE TABLE IF NOT EXISTS supplier_invoices_invoice (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    supplier_name       TEXT NOT NULL,
    supplier_tax_id     TEXT NOT NULL DEFAULT '',
    invoice_number      TEXT NOT NULL,
    invoice_date        TEXT,                               -- ISO YYYY-MM-DD (o NULL)
    due_date            TEXT,                               -- ISO YYYY-MM-DD (o NULL)
    payment_date        TEXT,                               -- ISO YYYY-MM-DD (o NULL)
    total_amount        NUMERIC NOT NULL DEFAULT 0,         -- suma de line_total (lo calcula el handler WASM)
    tax_amount          NUMERIC NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'pending',    -- pending|validated|paid|cancelled
    purchase_order_ref  TEXT NOT NULL DEFAULT '',           -- referencia libre (sin FK aún a purchase_orders)
    notes               TEXT NOT NULL DEFAULT '',
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT
);
CREATE INDEX IF NOT EXISTS ix_si_hub                ON supplier_invoices_invoice (hub_id, is_deleted);
CREATE INDEX IF NOT EXISTS ix_si_hub_status         ON supplier_invoices_invoice (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_si_hub_supplier       ON supplier_invoices_invoice (hub_id, supplier_name);
CREATE INDEX IF NOT EXISTS ix_si_hub_invoice_date   ON supplier_invoices_invoice (hub_id, invoice_date);

-- Línea de factura de proveedor (line_total = quantity * unit_price; lo calcula el handler WASM).
CREATE TABLE IF NOT EXISTS supplier_invoices_line (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    invoice_id    TEXT NOT NULL,
    description   TEXT NOT NULL,
    quantity      NUMERIC NOT NULL DEFAULT 1,
    unit_price    NUMERIC NOT NULL DEFAULT 0,
    line_total    NUMERIC NOT NULL DEFAULT 0,
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT,
    FOREIGN KEY (invoice_id) REFERENCES supplier_invoices_invoice (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_si_line_hub     ON supplier_invoices_line (hub_id, is_deleted);
CREATE INDEX IF NOT EXISTS ix_si_line_invoice ON supplier_invoices_line (hub_id, invoice_id);
