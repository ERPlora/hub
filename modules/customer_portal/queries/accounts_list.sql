-- Lista de cuentas de portal del hub, con filtro opcional por status. Runtime inyecta :hub_id.
-- Portado de PortalService.list_accounts. El bind :status: '' = sin filtro.
SELECT id, customer_name, customer_email, customer_tax_id, status,
       email_verified, language, invited_at, activated_at, last_login_at,
       notes, created_at
FROM customer_portal_account
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
ORDER BY created_at DESC;
