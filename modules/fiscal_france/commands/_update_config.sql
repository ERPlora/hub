-- Helper (invocado por el handler WASM update_config): actualización de config fiscal existente.
-- Runtime inyecta :current_user_id, :now. La validación va en el WASM — ver WASM-TODO.
UPDATE fiscal_france_config
SET siret = :siret,
    siren = :siren,
    company_name = :company_name,
    chorus_pro_environment = :chorus_pro_environment,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :config_id AND hub_id = :hub_id AND is_deleted = 0;
