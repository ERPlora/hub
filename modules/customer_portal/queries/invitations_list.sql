-- Invitaciones pendientes/usadas del hub. Runtime inyecta :hub_id.
-- Sin equivalente directo en services.py (sólo accept consume el token); útil para la UI.
SELECT id, customer_email, customer_name, invitation_token, invited_by_ref,
       expires_at, used_at, created_at
FROM customer_portal_invitation
WHERE hub_id = :hub_id AND is_deleted = 0
ORDER BY created_at DESC;
