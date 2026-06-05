-- Detalle de un contrato concreto. Runtime inyecta :hub_id.
-- Portado de ContractService.get_contract (los hitos se piden aparte con
-- contracts.milestones.list para no acoplar la query a un JOIN).
SELECT id, contract_number, customer_name, customer_email, customer_tax_id,
       contract_type, status, start_date, end_date,
       monthly_amount, total_amount, auto_renew, renewal_period_months,
       notes, terms, created_at
FROM contracts_contract
WHERE hub_id = :hub_id AND is_deleted = 0
  AND id = :contract_id;
