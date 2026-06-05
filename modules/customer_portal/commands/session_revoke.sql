-- Revoca una sesión (logout / revocación admin): is_active → 0. NO borra la fila.
-- Runtime inyecta :hub_id, :current_user_id, :now. Portado de PortalService.revoke_session.
-- Solo sesiones aún activas (guarda en el WHERE).
UPDATE customer_portal_session
SET is_active = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :session_id AND hub_id = :hub_id AND is_deleted = 0
  AND is_active = 1;
