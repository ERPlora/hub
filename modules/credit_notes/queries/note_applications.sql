-- Aplicaciones (contra facturas) de una nota de abono.
-- Portado de CreditNoteService.get_credit_note (applications).
SELECT id, credit_note_id, invoice_ref, amount_applied, applied_at
FROM credit_notes_application
WHERE credit_note_id = :cn_id AND hub_id = :hub_id AND is_deleted = 0
ORDER BY applied_at ASC;
