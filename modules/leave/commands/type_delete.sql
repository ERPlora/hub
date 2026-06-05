-- Soft-delete de tipo de ausencia (no borra: marca is_deleted + lo desactiva).
-- Portado de LeaveTypeService.delete_leave_type. El bloqueo "tipo referenciado por N
-- solicitudes, re-clasifícalas primero" requiere leer leave_request y devolver el conteo
-- afectado → va a runtime/WASM (ver WASM-TODO). Esta sentencia es el efecto final.
UPDATE leave_type
SET is_active  = 0,
    is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :leave_type_id AND hub_id = :hub_id AND is_deleted = 0;
