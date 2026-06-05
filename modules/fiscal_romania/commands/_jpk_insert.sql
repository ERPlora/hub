-- Helper interno: inserta una declaración JPK ya generada (estado 'generated', con XML).
-- Lo invoca el handler WASM tras validar tipo, periodo e importe y componer el XML.
-- Runtime inyecta :hub_id, :current_user_id, :now.
INSERT INTO fiscal_romania_jpk
  (id, hub_id, declaration_type, period_start, period_end, status,
   xml_content, total_amount,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :declaration_type, :period_start, :period_end, 'generated',
   :xml_content, :total_amount,
   0, :current_user_id, :current_user_id, :now, :now);
