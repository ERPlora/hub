-- Helper interno (intención del handler WASM assign_atcud). El WASM resuelve serie_cert desde
-- la config, compone el atcud (<serie_cert>-<seq>), encadena el hash y marca signed.
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now. Ver WASM-TODO §4.
INSERT INTO fiscal_portugal_atcud
  (id, hub_id, document_type, document_series_code, document_number, atcud,
   invoice_ref, hash_value, hash_method, signed,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :document_type, :document_series_code, :document_number, :atcud,
   :invoice_ref, :hash_value, :hash_method, :signed,
   0, :current_user_id, :current_user_id, :now, :now);
