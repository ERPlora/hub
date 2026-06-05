-- Un contrato de facturación por id (scope hub_id). Portado de ProjectBillingService.get_or_error.
SELECT id, contract_number, project_ref, customer_name, billing_type,
       total_amount, hourly_rate, currency, start_date, end_date, status,
       notes, created_at
FROM project_billing_contract
WHERE id = :contract_id AND hub_id = :hub_id AND is_deleted = 0;
