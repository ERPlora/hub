-- Sub-paso de los handlers WASM apply_to_invoice / unapply / cancel_credit_note:
-- fija applied_amount y status recalculados por el handler (issued|applied|cancelled).
-- Mantiene applied_amount sincronizado con la suma de aplicaciones vivas.
UPDATE credit_notes_note
SET applied_amount = :applied_amount,
    status = :status,
    notes = :notes,
    reason = :reason,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :cn_id AND hub_id = :hub_id AND is_deleted = 0;
