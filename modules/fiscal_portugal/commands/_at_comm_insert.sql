-- Helper interno (intención del handler WASM create_at_communication). El WASM compone
-- document_number (ATC-YYYYMMDD-NNNN) y el XML; el runtime persiste la fila en draft.
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now. Ver WASM-TODO §5.
INSERT INTO fiscal_portugal_at_comm
  (id, hub_id, document_number, communication_type, reference_period,
   content_xml, submission_id, status, submitted_at,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :document_number, :communication_type, :reference_period,
   :content_xml, '', 'draft', NULL,
   0, :current_user_id, :current_user_id, :now, :now);
