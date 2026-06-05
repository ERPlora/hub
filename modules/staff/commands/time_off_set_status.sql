-- Cambio de estado de una solicitud de ausencia (approve/reject/cancel).
-- Runtime inyecta :hub_id, :current_user_id, :now. Si :status = 'approved' sella el aprobador.
-- La transición simple cabe en una sentencia; la validación de transiciones permitidas y el
-- chequeo de solapamiento al aprobar va a runtime — ver WASM-TODO.
UPDATE staff_time_off
SET status      = :status,
    approved_by = CASE WHEN :status = 'approved' THEN :current_user_id ELSE approved_by END,
    approved_at = CASE WHEN :status = 'approved' THEN :now ELSE approved_at END,
    updated_by  = :current_user_id,
    updated_at  = :now
WHERE id = :time_off_id AND hub_id = :hub_id AND is_deleted = 0;
