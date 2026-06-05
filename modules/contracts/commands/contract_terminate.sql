-- Transición active|suspended → terminated. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de ContractService.terminate_contract. Solo afecta a contratos en estado
-- 'active' o 'suspended'. El rastro textual [TERMINATED] reason en notes NO se escribe
-- aquí (append con timestamp = capacidad de reloj del host) — ver WASM-TODO.
UPDATE contracts_contract
SET status = 'terminated',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :contract_id AND hub_id = :hub_id AND is_deleted = 0
  AND status IN ('active', 'suspended');
