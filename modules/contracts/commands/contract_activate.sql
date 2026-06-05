-- Transición draft → active. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de ContractService.activate_contract. El guard de estado va en el WHERE:
-- solo afecta a contratos en 'draft' (0 filas afectadas = transición inválida, que
-- el runtime traduce a error invalid_state — ver WASM-TODO).
UPDATE contracts_contract
SET status = 'active',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :contract_id AND hub_id = :hub_id AND is_deleted = 0
  AND status = 'draft';
