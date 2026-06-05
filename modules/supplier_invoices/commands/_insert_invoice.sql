-- Inserta la cabecera de factura de proveedor. Lo invoca el handler WASM `create_invoice`
-- tras calcular total_amount como suma de los line_total. Runtime inyecta :hub_id, :current_user_id, :now.
-- :invoice_id lo aporta el handler (es el mismo id que comparten las líneas).
INSERT INTO supplier_invoices_invoice (
    id, hub_id, supplier_name, supplier_tax_id, invoice_number,
    invoice_date, due_date, payment_date,
    total_amount, tax_amount, status, purchase_order_ref, notes,
    is_deleted, created_by, updated_by, created_at, updated_at
) VALUES (
    :invoice_id, :hub_id, :supplier_name, :supplier_tax_id, :invoice_number,
    :invoice_date, :due_date, NULL,
    :total_amount, :tax_amount, 'pending', :purchase_order_ref, :notes,
    0, :current_user_id, :current_user_id, :now, :now
);
