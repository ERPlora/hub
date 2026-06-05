-- Borrado lógico de un registro de tiempo. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de TimesheetService.delete_entry. Guarda de estado: NO borra registros
-- aprobados (status='approved' queda excluido por el WHERE → 0 filas afectadas =
-- el runtime devuelve "no encontrado o aprobado").
UPDATE timesheets_time_entry
SET is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :entry_id AND hub_id = :hub_id AND is_deleted = 0 AND status != 'approved';
