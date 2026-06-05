-- Lista de notas de abono del hub con filtros opcionales (direction/status/counterparty_name).
-- Portado de CreditNoteService.list_credit_notes. Runtime inyecta :hub_id.
-- Los filtros usan el patrón "param vacío => sin filtro" (:direction='' deja pasar todo).
SELECT id, credit_note_number, direction, counterparty_name, counterparty_tax_id,
       issue_date, original_invoice_ref, total_amount, tax_amount, applied_amount,
       reason, status, notes, created_at
FROM credit_notes_note
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:direction = '' OR direction = :direction)
  AND (:status = '' OR status = :status)
  AND (:counterparty_name = '' OR counterparty_name LIKE '%' || :counterparty_name || '%')
ORDER BY created_at DESC
LIMIT :limit;
