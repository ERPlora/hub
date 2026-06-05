-- Lista de sesiones del portal, con filtros opcionales por cuenta y solo activas.
-- Runtime inyecta :hub_id. Portado de PortalService.list_sessions.
-- Binds: :account_id ('' = todas) · :active_only (1 = solo activas, 0 = todas).
SELECT id, account_id, session_token, expires_at, is_active,
       ip_address, user_agent, created_at
FROM customer_portal_session
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:account_id = '' OR account_id = :account_id)
  AND (:active_only = 0 OR is_active = 1)
ORDER BY created_at DESC;
