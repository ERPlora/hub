-- Sub-paso del handler WASM apply_to_invoice: inserta una aplicación contra una factura.
-- El handler valida que (already + amount) <= total antes de llamar aquí (over_applied).
INSERT INTO credit_notes_application
  (id, hub_id, credit_note_id, invoice_ref, amount_applied, applied_at,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :credit_note_id, :invoice_ref, :amount_applied, :now,
   0, :current_user_id, :current_user_id, :now, :now);
