-- Una factura de proyecto por id (scope hub_id). Incluye el snapshot JSON line_items.
SELECT id, contract_id, invoice_number, invoice_date, due_date, amount,
       status, line_items, created_at
FROM project_billing_invoice
WHERE id = :invoice_id AND hub_id = :hub_id AND is_deleted = 0;
