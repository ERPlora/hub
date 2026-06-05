-- Transición draft -> issued (Tier 0 declarativo). Portado de CreditNoteService.issue_credit_note.
-- Si no había issue_date la fija a :now (fecha de hoy la inyecta el runtime).
-- Solo afecta a notas en estado 'draft' (el WHERE protege el invariante de estado).
UPDATE credit_notes_note
SET status = 'issued',
    issue_date = COALESCE(NULLIF(issue_date, ''), :issue_date),
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :cn_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'draft';
