-- Edición de cuenta (campos no sensibles + activación). Runtime inyecta :hub_id, :current_user_id, :now.
-- La rotación de credenciales cifradas va por un command dedicado (ver WASM-TODO.md).
UPDATE communications_account
SET name          = :name,
    email_address = :email_address,
    imap_host     = :imap_host,
    imap_port     = :imap_port,
    imap_username = :imap_username,
    imap_use_ssl  = :imap_use_ssl,
    smtp_host     = :smtp_host,
    smtp_port     = :smtp_port,
    smtp_username = :smtp_username,
    smtp_use_tls  = :smtp_use_tls,
    is_active     = :is_active,
    updated_by    = :current_user_id,
    updated_at    = :now
WHERE hub_id = :hub_id AND id = :id AND is_deleted = 0;
