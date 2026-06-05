-- Cierra una cuenta de portal (estado terminal). Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de PortalService.close_account. El append de [CLOSED] reason a notes va a WASM —
-- ver WASM-TODO. Solo cuentas no cerradas ya (guarda en el WHERE).
UPDATE customer_portal_account
SET status = 'closed',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :account_id AND hub_id = :hub_id AND is_deleted = 0
  AND status != 'closed';
