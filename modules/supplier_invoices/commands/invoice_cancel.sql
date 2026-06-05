-- Cancela una factura (cualquier estado salvo 'paid'). Portado de SupplierInvoiceService.cancel_invoice.
-- El guard (status <> 'paid' y <> 'cancelled') va en el WHERE; :reason se anexa a notes.
UPDATE supplier_invoices_invoice
SET status = 'cancelled',
    notes = TRIM(notes || char(10) || '[CANCELLED] ' || :reason),
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :invoice_id AND hub_id = :hub_id AND is_deleted = 0
  AND status NOT IN ('paid', 'cancelled');
