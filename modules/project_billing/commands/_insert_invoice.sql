-- Comando privado (helper de handler WASM). Inserta la cabecera de factura con el snapshot JSON
-- de líneas ya calculado por el WASM. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- invoice_number, amount y line_items vienen ya resueltos por generate_invoice (ver WASM-TODO §2).
INSERT INTO project_billing_invoice
  (id, hub_id, contract_id, invoice_number, invoice_date, due_date, amount,
   status, line_items, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :contract_id, :invoice_number, :invoice_date, :due_date, :amount,
   'draft', :line_items, 0, :current_user_id, :current_user_id, :now, :now);
