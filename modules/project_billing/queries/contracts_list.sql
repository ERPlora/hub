-- Lista de contratos de facturación del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de ProjectBillingService.list_contracts. Los binds opcionales se pasan como '' = sin filtro.
SELECT id, contract_number, project_ref, customer_name, billing_type,
       total_amount, hourly_rate, currency, start_date, end_date, status,
       notes, created_at
FROM project_billing_contract
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:project_ref  = '' OR project_ref  = :project_ref)
  AND (:status       = '' OR status       = :status)
  AND (:billing_type = '' OR billing_type = :billing_type)
ORDER BY created_at DESC
LIMIT :limit;
