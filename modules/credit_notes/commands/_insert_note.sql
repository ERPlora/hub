-- Sub-paso del handler WASM create_credit_note: inserta la cabecera de la nota (draft).
-- El número (CN-YYYYMMDD-NNNN) y el total lo calcula/asigna el handler; aquí solo persiste.
-- Runtime inyecta :hub_id, :current_user_id, :now.
INSERT INTO credit_notes_note
  (id, hub_id, credit_note_number, direction, counterparty_name, counterparty_tax_id,
   issue_date, original_invoice_ref, total_amount, tax_amount, applied_amount,
   reason, status, notes,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :credit_note_number, :direction, :counterparty_name, :counterparty_tax_id,
   :issue_date, :original_invoice_ref, :total_amount, :tax_amount, 0,
   :reason, 'draft', :notes,
   0, :current_user_id, :current_user_id, :now, :now);
