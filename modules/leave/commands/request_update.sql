-- Edición de una solicitud que sigue 'pending'. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de LeaveService.update_request. El guard status='pending' está en el WHERE: si la
-- solicitud no está pendiente, no se actualiza ninguna fila (workflow-final inmutable).
-- COALESCE permite parches parciales. La validación end_date >= start_date va en el schema/runtime.
UPDATE leave_request
SET start_date = COALESCE(:start_date, start_date),
    end_date   = COALESCE(:end_date, end_date),
    reason     = COALESCE(:reason, reason),
    notes      = COALESCE(:notes, notes),
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :request_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'pending';
