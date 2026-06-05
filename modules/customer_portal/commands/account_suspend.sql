-- Suspende una cuenta de portal (active → suspended). Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de PortalService.suspend_account. La guarda de estado (no suspender 'closed' ni
-- re-suspender, y el append de [SUSPENDED] reason a notes) va a WASM — ver WASM-TODO.
-- Aquí la guarda mínima vive en el WHERE: solo cuentas no cerradas ni ya suspendidas.
UPDATE customer_portal_account
SET status = 'suspended',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :account_id AND hub_id = :hub_id AND is_deleted = 0
  AND status NOT IN ('suspended', 'closed');
