-- Líneas de una factura de proveedor (scope hub_id). Portado de SupplierInvoiceService.get_invoice (lines).
SELECT id, invoice_id, description, quantity, unit_price, line_total
FROM supplier_invoices_line
WHERE invoice_id = :invoice_id AND hub_id = :hub_id AND is_deleted = 0
ORDER BY created_at ASC;
