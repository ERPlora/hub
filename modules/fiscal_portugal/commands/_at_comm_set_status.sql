-- Helper interno (intención del handler WASM update_communication_status). El WASM valida que
-- el estado actual permita la transición (submitted|accepted|rejected -> accepted|rejected|submitted).
-- Runtime inyecta :current_user_id, :now. Ver WASM-TODO §7.
UPDATE fiscal_portugal_at_comm
SET status     = :new_status,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :comm_id AND hub_id = :hub_id AND is_deleted = 0
  AND status IN ('submitted', 'accepted', 'rejected');
