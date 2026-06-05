-- Una nota de abono por id (scope hub_id). Portado de CreditNoteService.get_credit_note (cabecera).
-- Las líneas y aplicaciones se piden aparte (credit_notes.notes.lines / .applications).
SELECT id, credit_note_number, direction, counterparty_name, counterparty_tax_id,
       issue_date, original_invoice_ref, total_amount, tax_amount, applied_amount,
       reason, status, notes, created_at
FROM credit_notes_note
WHERE id = :cn_id AND hub_id = :hub_id AND is_deleted = 0;
