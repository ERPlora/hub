-- Comando privado (helper de handler WASM). Setea el estado de un hito y, según corresponda,
-- invoiced_at / paid_at. Usado por generate_invoice (→ 'invoiced') y mark_invoice_paid (→ 'paid').
-- Runtime inyecta :current_user_id, :now. Los binds :invoiced_at / :paid_at se pasan ya resueltos
-- (ISO 8601 o NULL) por el WASM.
UPDATE project_billing_milestone
SET status = :status,
    invoiced_at = :invoiced_at,
    paid_at = :paid_at,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :milestone_id AND hub_id = :hub_id AND is_deleted = 0;
