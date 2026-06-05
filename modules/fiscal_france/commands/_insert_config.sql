-- Helper (invocado por el handler WASM update_config): alta de config fiscal.
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now. La validación SIRET/SIREN
-- y la decisión insert/update la toma el WASM — ver WASM-TODO.
INSERT INTO fiscal_france_config
  (id, hub_id, siret, siren, company_name, chorus_pro_environment, chorus_credentials_hash,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :siret, :siren, :company_name, :chorus_pro_environment, '',
   0, :current_user_id, :current_user_id, :now, :now);
