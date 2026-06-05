-- Helper interno: alta o actualización de la config fiscal (una por hub).
-- Invocado por el handler WASM tras validar CIF y entorno. Runtime inyecta
-- :new_id, :hub_id, :current_user_id, :now. El handler decide INSERT vs UPDATE
-- según exista ya config (ON CONFLICT sobre (hub_id, company_cif) no cubre el
-- caso de cambio de CIF, por eso la decisión la toma el WASM con el id existente).
INSERT INTO fiscal_romania_config
  (id, hub_id, company_cif, company_name, anaf_environment, api_key_hash,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:id, :hub_id, :company_cif, :company_name, :anaf_environment, '',
   0, :current_user_id, :current_user_id, :now, :now)
ON CONFLICT (id) DO UPDATE SET
   company_cif      = :company_cif,
   company_name     = :company_name,
   anaf_environment = :anaf_environment,
   updated_by       = :current_user_id,
   updated_at       = :now;
