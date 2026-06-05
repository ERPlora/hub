-- Cancelación de una solicitud (cambio de estado suave a 'cancelled', NO hard-delete).
-- Portado de LeaveService.cancel_request. Solo desde 'pending' (el caso 'approved' requiere
-- override de manager desde la UI y los rollups de saldo → ver WASM-TODO). Runtime inyecta binds.
UPDATE leave_request
SET status     = 'cancelled',
    notes      = TRIM(notes || CASE WHEN :reason = '' THEN '' ELSE char(10) || '[cancelled] ' || :reason END),
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :request_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'pending';
