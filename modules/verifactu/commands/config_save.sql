-- Guardar/crear la configuración VeriFactu del hub (UPSERT por hub_id).
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de routes.settings_view (POST). El runtime cifra certificate_password.
-- ON CONFLICT(hub_id) hace UPDATE: el índice único ix_verifactu_config_hub lo garantiza.
INSERT INTO verifactu_config
  (id, hub_id, enabled, mode, environment,
   software_name, software_version, software_id, software_nif,
   certificate_path, certificate_password, certificate_expiry,
   auto_transmit, retry_interval_minutes, max_retries,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :enabled, :mode, :environment,
   :software_name, :software_version, :software_id, :software_nif,
   :certificate_path, :certificate_password, :certificate_expiry,
   :auto_transmit, :retry_interval_minutes, :max_retries,
   0, :current_user_id, :current_user_id, :now, :now)
ON CONFLICT(hub_id) DO UPDATE SET
   enabled                = excluded.enabled,
   mode                   = excluded.mode,
   environment            = excluded.environment,
   software_name          = excluded.software_name,
   software_version       = excluded.software_version,
   software_id            = excluded.software_id,
   software_nif           = excluded.software_nif,
   certificate_path       = excluded.certificate_path,
   certificate_password   = excluded.certificate_password,
   certificate_expiry     = excluded.certificate_expiry,
   auto_transmit          = excluded.auto_transmit,
   retry_interval_minutes = excluded.retry_interval_minutes,
   max_retries            = excluded.max_retries,
   updated_by             = :current_user_id,
   updated_at             = :now;
