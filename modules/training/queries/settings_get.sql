-- Configuración de formación del hub (singleton). Runtime inyecta :hub_id.
-- Portado de _get_settings / settings_page. La creación lazy del singleton la hace el
-- command training.settings.save (ver WASM-TODO: upsert por hub_id).
SELECT id, require_completion_proof, auto_assign_mandatory, reminder_days_before,
       certificate_expiry_warning_days
FROM training_settings
WHERE hub_id = :hub_id AND is_deleted = 0
LIMIT 1;
