-- Cuentas conectadas del hub. NUNCA devuelve credenciales cifradas (passwords/tokens).
-- Portado de la gestión de cuentas (manage_accounts). El runtime inyecta :hub_id.
SELECT id, name, account_type, channel, owner_id, email_address,
       imap_host, imap_port, imap_username, imap_use_ssl,
       smtp_host, smtp_port, smtp_username, smtp_use_tls,
       is_active, last_sync_at, sync_status, sync_error
FROM communications_account
WHERE hub_id = :hub_id AND is_deleted = 0
ORDER BY name ASC;
