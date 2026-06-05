-- Lista de facturas de proyecto del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de ProjectBillingService / routes.list_invoices. Binds opcionales: '' = sin filtro.
SELECT id, contract_id, invoice_number, invoice_date, due_date, amount,
       status, line_items, created_at
FROM project_billing_invoice
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status      = '' OR status      = :status)
  AND (:contract_id = '' OR contract_id = :contract_id)
ORDER BY created_at DESC
LIMIT :limit;
