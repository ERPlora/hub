-- Una cuenta de portal por id. Runtime inyecta :hub_id.
-- Portado de PortalService.get_account.
SELECT id, customer_name, customer_email, customer_tax_id, status,
       email_verified, language, invited_at, activated_at, last_login_at,
       notes, created_at
FROM customer_portal_account
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :account_id;
