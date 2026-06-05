-- Actualización de la config fiscal alemana existente. Lo invoca el handler WASM (upsert_config).
-- Runtime inyecta :current_user_id, :now.
UPDATE fiscal_germany_config
SET ust_id = :ust_id,
    steuernummer = :steuernummer,
    company_name = :company_name,
    leitweg_id_default = :leitweg_id_default,
    xrechnung_environment = :xrechnung_environment,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :config_id AND hub_id = :hub_id AND is_deleted = 0;
