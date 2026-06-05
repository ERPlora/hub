-- Una factura de proveedor por id (scope hub_id). Portado de SupplierInvoiceService.get_invoice.
-- Las líneas se piden aparte con supplier_invoices.invoices.lines.
SELECT id, supplier_name, supplier_tax_id, invoice_number,
       invoice_date, due_date, payment_date,
       total_amount, tax_amount, status, purchase_order_ref, notes, created_at
FROM supplier_invoices_invoice
WHERE id = :invoice_id AND hub_id = :hub_id AND is_deleted = 0;
