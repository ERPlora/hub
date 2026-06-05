-- Configuración VeriFactu del hub (singleton). Runtime inyecta :hub_id.
-- Portado de VerifactuService.get_config / settings_view. No expone certificate_password.
SELECT id, enabled, mode, environment,
       software_name, software_version, software_id, software_nif,
       certificate_path, certificate_expiry,
       auto_transmit, retry_interval_minutes, max_retries
FROM verifactu_config
WHERE hub_id = :hub_id AND is_deleted = 0
LIMIT 1;
