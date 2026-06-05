-- Transición active → suspended. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de ContractService.suspend_contract. Solo afecta a contratos 'active'.
-- El rastro textual [SUSPENDED] reason en notes NO se escribe aquí (append con
-- timestamp = capacidad de reloj del host) — ver WASM-TODO.
UPDATE contracts_contract
SET status = 'suspended',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :contract_id AND hub_id = :hub_id AND is_deleted = 0
  AND status = 'active';
