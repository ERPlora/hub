-- Desbloqueo de cliente (vuelve a 'active'). Runtime inyecta :current_user_id, :now.
-- Portado de CreditRiskService.unblock_customer. La guarda "no estaba bloqueado" + el registro
-- del CreditEvent 'manual_review' van a runtime/WASM (ver WASM-TODO §customer_unblock).
UPDATE credit_risk_customer
SET status = 'active',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :customer_credit_id AND hub_id = :hub_id AND is_deleted = 0
  AND status = 'blocked';
