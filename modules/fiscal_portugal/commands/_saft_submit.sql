-- Helper interno (intención del handler WASM submit_saft). El WASM valida la transición de
-- estado (solo 'generated' -> 'submitted' y xml_content presente) antes de pedir este UPDATE.
-- Runtime inyecta :current_user_id, :now. Ver WASM-TODO §3.
UPDATE fiscal_portugal_saft
SET status       = 'submitted',
    submitted_at = :now,
    updated_by   = :current_user_id,
    updated_at   = :now
WHERE id = :saft_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'generated';
