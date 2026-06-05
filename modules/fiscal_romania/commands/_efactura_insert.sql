-- Helper interno: inserta una e-Factura en estado 'draft'. Lo invoca el handler
-- WASM tras generar el document_number atómico (EFR-YYYYMMDD-NNNN) y validar CIFs
-- e importes. Runtime inyecta :hub_id, :current_user_id, :now.
INSERT INTO fiscal_romania_efactura
  (id, hub_id, document_number, invoice_ref, document_type,
   supplier_cif, customer_cif, total_amount, vat_amount, status,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :document_number, :invoice_ref, :document_type,
   :supplier_cif, :customer_cif, :total_amount, :vat_amount, 'draft',
   0, :current_user_id, :current_user_id, :now, :now);
