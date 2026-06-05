-- Helper (invocado por el handler WASM create_facturx): alta de documento Factur-X en draft.
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now. El nº (:document_number),
-- la validación SIRET y el cálculo de TTC (= HT + IVA) los hace el WASM — ver WASM-TODO.
INSERT INTO fiscal_france_facturx
  (id, hub_id, document_number, invoice_ref, supplier_siret, customer_siret,
   total_amount_ht, vat_amount, total_amount_ttc, status, xml_zugferd_content,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :document_number, :invoice_ref, :supplier_siret, :customer_siret,
   :total_amount_ht, :vat_amount, :total_amount_ttc, 'draft', '',
   0, :current_user_id, :current_user_id, :now, :now);
