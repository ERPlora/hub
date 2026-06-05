-- Transición draft → sent de una factura de proyecto. Runtime inyecta :current_user_id, :now.
-- Portado de ProjectBillingService.mark_invoice_sent. WHERE status='draft' refuerza la guarda.
UPDATE project_billing_invoice
SET status = 'sent',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :invoice_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'draft';
