-- Transición active → completed de un contrato. Runtime inyecta :current_user_id, :now.
-- Portado de ProjectBillingService.close_contract. WHERE status='active' refuerza la guarda.
UPDATE project_billing_contract
SET status = 'completed',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :contract_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'active';
