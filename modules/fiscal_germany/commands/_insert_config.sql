-- Alta de la config fiscal alemana del hub. Lo invoca el handler WASM (upsert_config)
-- tras validar el formato del USt-IdNr. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
INSERT INTO fiscal_germany_config
  (id, hub_id, ust_id, steuernummer, company_name, leitweg_id_default, xrechnung_environment,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :ust_id, :steuernummer, :company_name, :leitweg_id_default, :xrechnung_environment,
   0, :current_user_id, :current_user_id, :now, :now);
