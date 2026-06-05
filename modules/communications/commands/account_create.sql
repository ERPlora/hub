-- Alta de cuenta de comunicaciones. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Las contraseñas IMAP/SMTP en claro NO se persisten aquí: el cifrado (crypto.py) lo hace
-- una capability del host antes de pasar :imap_password_encrypted/:smtp_password_encrypted.
-- Ver WASM-TODO.md (cifrado de credenciales + vínculo cuenta↔grupos).
INSERT INTO communications_account
  (id, hub_id, name, account_type, channel, owner_id, email_address,
   imap_host, imap_port, imap_username, imap_password_encrypted, imap_use_ssl,
   smtp_host, smtp_port, smtp_username, smtp_password_encrypted, smtp_use_tls,
   is_active, sync_status, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :account_type, :channel, :owner_id, :email_address,
   :imap_host, :imap_port, :imap_username, :imap_password_encrypted, :imap_use_ssl,
   :smtp_host, :smtp_port, :smtp_username, :smtp_password_encrypted, :smtp_use_tls,
   1, 'idle', 0, :current_user_id, :current_user_id, :now, :now);
