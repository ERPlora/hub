-- Bloqueo de cliente (no se le extiende más crédito). Runtime inyecta :current_user_id, :now.
-- Portado de CreditRiskService.block_customer. La guarda "ya bloqueado" + el registro del
-- CreditEvent 'manual_review' asociado van a runtime/WASM (ver WASM-TODO §customer_block).
-- Aquí solo se cambia el estado y se anexa el motivo a notes.
UPDATE credit_risk_customer
SET status = 'blocked',
    notes = TRIM(notes || char(10) || '[BLOCKED] ' || :reason),
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :customer_credit_id AND hub_id = :hub_id AND is_deleted = 0
  AND status != 'blocked';
