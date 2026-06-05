-- Líneas de una nota de abono. Portado de CreditNoteService.get_credit_note (lines).
SELECT id, credit_note_id, description, quantity, unit_price, line_total, tax_rate
FROM credit_notes_line
WHERE credit_note_id = :cn_id AND hub_id = :hub_id AND is_deleted = 0
ORDER BY created_at ASC;
