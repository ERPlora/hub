-- Transición draft → active de un contrato. Runtime inyecta :current_user_id, :now.
-- Portado de ProjectBillingService.activate_contract. La guarda de estado (solo desde 'draft')
-- la refuerza el WHERE status='draft': si no estaba en draft, 0 filas afectadas → el runtime
-- lo trata como error de estado inválido.
UPDATE project_billing_contract
SET status = 'active',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :contract_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'draft';
