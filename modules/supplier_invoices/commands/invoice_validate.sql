-- Transición pending → validated. Portado de SupplierInvoiceService.validate_invoice.
-- El guard de estado (solo 'pending') va en el WHERE: si la fila no está pending no se actualiza.
UPDATE supplier_invoices_invoice
SET status = 'validated',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :invoice_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'pending';
