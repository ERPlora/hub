-- Hitos de facturación de un contrato. Runtime inyecta :hub_id.
-- Portado de ContractService.get_contract (sección de milestones).
SELECT id, contract_id, description, due_date, amount, is_invoiced, invoiced_at
FROM contracts_milestone
WHERE hub_id = :hub_id AND is_deleted = 0
  AND contract_id = :contract_id
ORDER BY due_date ASC, created_at ASC;
