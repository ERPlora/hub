-- Crédito restante de una nota: total_amount - applied_amount (columna cacheada).
-- Portado de CreditNoteService.get_remaining_credit.
SELECT id, credit_note_number, total_amount, applied_amount,
       (total_amount - applied_amount) AS remaining_credit
FROM credit_notes_note
WHERE id = :cn_id AND hub_id = :hub_id AND is_deleted = 0;
