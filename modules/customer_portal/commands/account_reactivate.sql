-- Reactiva una cuenta suspendida (suspended → active). Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de PortalService.reactivate_account. Solo cuentas en 'suspended' (guarda en el WHERE).
UPDATE customer_portal_account
SET status = 'active',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :account_id AND hub_id = :hub_id AND is_deleted = 0
  AND status = 'suspended';
