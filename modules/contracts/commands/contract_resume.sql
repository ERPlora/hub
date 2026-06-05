-- Transición suspended → active. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de ContractService.resume_contract. Solo afecta a contratos 'suspended'.
UPDATE contracts_contract
SET status = 'active',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :contract_id AND hub_id = :hub_id AND is_deleted = 0
  AND status = 'suspended';
