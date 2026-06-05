-- Helper interno (intención del handler WASM update_config) cuando ya existe config para el hub.
-- Runtime inyecta :current_user_id, :now. Ver WASM-TODO §1.
UPDATE fiscal_portugal_config
SET nif                      = :nif,
    company_name             = :company_name,
    at_environment           = :at_environment,
    serie_certification_code = :serie_certification_code,
    updated_by               = :current_user_id,
    updated_at               = :now
WHERE id = :config_id AND hub_id = :hub_id AND is_deleted = 0;
