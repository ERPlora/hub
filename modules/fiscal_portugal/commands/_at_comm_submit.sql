-- Helper interno (intención del handler WASM submit_at_communication). El WASM valida la
-- transición (solo 'draft' -> 'submitted') y compone submission_id (PENDING-<document_number>).
-- Runtime inyecta :current_user_id, :now. Ver WASM-TODO §6.
UPDATE fiscal_portugal_at_comm
SET status        = 'submitted',
    submitted_at  = :now,
    submission_id = :submission_id,
    updated_by    = :current_user_id,
    updated_at    = :now
WHERE id = :comm_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'draft';
