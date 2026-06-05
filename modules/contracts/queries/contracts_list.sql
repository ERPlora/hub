-- Lista de contratos del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de ContractService.list_contracts. Filtros opcionales por estado y por
-- nombre de cliente (LIKE). Pasar '' en un bind = sin ese filtro.
SELECT id, contract_number, customer_name, customer_email, customer_tax_id,
       contract_type, status, start_date, end_date,
       monthly_amount, total_amount, auto_renew, renewal_period_months,
       notes, terms, created_at
FROM contracts_contract
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
  AND (:customer_name = '' OR customer_name LIKE '%' || :customer_name || '%')
ORDER BY created_at DESC
LIMIT :limit;
