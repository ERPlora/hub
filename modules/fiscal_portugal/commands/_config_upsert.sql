-- Helper interno (intención del handler WASM update_config). El WASM resuelve si es alta o
-- actualización (la config es única por hub) y el runtime ejecuta el INSERT correspondiente.
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now. Ver WASM-TODO §1.
INSERT INTO fiscal_portugal_config
  (id, hub_id, nif, company_name, at_environment, at_credentials_hash,
   serie_certification_code, software_certification_number,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :nif, :company_name, :at_environment, :at_credentials_hash,
   :serie_certification_code, :software_certification_number,
   0, :current_user_id, :current_user_id, :now, :now);
