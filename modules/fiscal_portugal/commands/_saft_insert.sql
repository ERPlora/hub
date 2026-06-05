-- Helper interno (intención del handler WASM generate_saft). El WASM compone document_number
-- (SAFT-YYYYMMDD-NNNN), el XML SAF-T PT y los totales; el runtime persiste la fila.
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now. Ver WASM-TODO §2.
INSERT INTO fiscal_portugal_saft
  (id, hub_id, document_number, period_start, period_end, period_type,
   xml_content, total_invoices, total_amount, status, generated_at, submitted_at,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :document_number, :period_start, :period_end, :period_type,
   :xml_content, :total_invoices, :total_amount, 'generated', :now, NULL,
   0, :current_user_id, :current_user_id, :now, :now);
