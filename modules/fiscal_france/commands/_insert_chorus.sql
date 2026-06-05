-- Helper (invocado por el handler WASM create_chorus_invoice): alta de factura Chorus Pro en draft.
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now. El nº (:document_number) y el
-- parseo del importe los hace el WASM — ver WASM-TODO.
INSERT INTO fiscal_france_chorus
  (id, hub_id, document_number, invoice_ref, recipient_service_code, total_amount,
   status, upload_id, anomaly_code,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :document_number, :invoice_ref, :recipient_service_code, :total_amount,
   'draft', '', '',
   0, :current_user_id, :current_user_id, :now, :now);
