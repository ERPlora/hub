-- Alta de un documento XRechnung en estado 'draft'. Lo invoca el handler WASM (create_xrechnung)
-- con el document_number ya calculado (XR-YYYYMMDD-NNNN) y los totales validados.
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
INSERT INTO fiscal_germany_xrechnung
  (id, hub_id, document_number, invoice_ref, supplier_ust_id, customer_leitweg_id,
   total_netto, total_steuer, total_brutto, status, xml_content, validation_errors, submission_date,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :document_number, :invoice_ref, :supplier_ust_id, :customer_leitweg_id,
   :total_netto, :total_steuer, :total_brutto, 'draft', '', NULL, NULL,
   0, :current_user_id, :current_user_id, :now, :now);
