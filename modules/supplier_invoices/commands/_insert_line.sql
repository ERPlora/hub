-- Inserta una línea de factura de proveedor (line_total precalculado por el handler WASM).
-- Runtime inyecta :hub_id, :current_user_id, :now. :line_id y :invoice_id los aporta el handler.
INSERT INTO supplier_invoices_line (
    id, hub_id, invoice_id, description, quantity, unit_price, line_total,
    is_deleted, created_by, updated_by, created_at, updated_at
) VALUES (
    :line_id, :hub_id, :invoice_id, :description, :quantity, :unit_price, :line_total,
    0, :current_user_id, :current_user_id, :now, :now
);
