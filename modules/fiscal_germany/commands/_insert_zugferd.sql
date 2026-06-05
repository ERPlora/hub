-- Alta de un documento ZUGFeRD. Lo invoca el handler WASM (create_zugferd) con el
-- document_number ya calculado (ZF-YYYYMMDD-NNNN) y el profile validado.
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
INSERT INTO fiscal_germany_zugferd
  (id, hub_id, document_number, invoice_ref, supplier_ust_id, customer_name,
   total_netto, total_brutto, profile, pdf_a3_path, xml_embedded,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :document_number, :invoice_ref, :supplier_ust_id, :customer_name,
   :total_netto, :total_brutto, :profile, '', '',
   0, :current_user_id, :current_user_id, :now, :now);
