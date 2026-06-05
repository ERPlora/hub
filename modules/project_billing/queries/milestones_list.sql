-- Hitos de un contrato (scope hub_id). Usado por la vista de contratos y por generate_invoice.
-- :status = '' devuelve todos; p.ej. 'pending' para los facturables.
SELECT id, contract_id, name, due_date, amount, status, invoiced_at, paid_at, created_at
FROM project_billing_milestone
WHERE hub_id = :hub_id AND is_deleted = 0
  AND contract_id = :contract_id
  AND (:status = '' OR status = :status)
ORDER BY due_date ASC, created_at ASC;
