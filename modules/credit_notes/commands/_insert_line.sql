-- Sub-paso del handler WASM create_credit_note: inserta una línea.
-- line_total = quantity * unit_price lo calcula el handler (CreditNoteLine.calculate).
INSERT INTO credit_notes_line
  (id, hub_id, credit_note_id, description, quantity, unit_price, line_total, tax_rate,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :credit_note_id, :description, :quantity, :unit_price, :line_total, :tax_rate,
   0, :current_user_id, :current_user_id, :now, :now);
