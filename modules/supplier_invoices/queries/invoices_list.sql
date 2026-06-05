-- Lista de facturas de proveedor del hub (más recientes primero). Runtime inyecta :hub_id.
-- Portado de SupplierInvoiceService.list_invoices (orden por created_at desc, límite 50).
-- El filtro por status / supplier_name del legacy se aplica en la UI/SDK sobre este resultado.
SELECT id, supplier_name, supplier_tax_id, invoice_number,
       invoice_date, due_date, payment_date,
       total_amount, tax_amount, status, purchase_order_ref
FROM supplier_invoices_invoice
WHERE hub_id = :hub_id AND is_deleted = 0
ORDER BY created_at DESC
LIMIT 50;
