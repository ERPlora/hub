-- Transición validated → paid (fija payment_date). Portado de SupplierInvoiceService.mark_paid.
-- El guard de estado (solo 'validated') va en el WHERE. :payment_date lo aporta la UI/SDK
-- (ISO YYYY-MM-DD); si llega vacío el SDK usa la fecha de hoy antes de enviar.
UPDATE supplier_invoices_invoice
SET status = 'paid',
    payment_date = :payment_date,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :invoice_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'validated';
