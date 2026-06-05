-- Baja (terminación) lógica de un miembro: NO se hard-borra (lo referencian nóminas,
-- fichajes, horarios... el rastro de auditoría debe sobrevivir). Portado de
-- StaffService.delete_staff_member: status='terminated' + termination_date=hoy + soft-delete.
-- Runtime inyecta :hub_id, :current_user_id, :now (:today = fecha ISO).
UPDATE staff_member
SET status           = 'terminated',
    is_bookable      = 0,
    termination_date = COALESCE(termination_date, :today),
    is_deleted       = 1,
    deleted_at       = :now,
    updated_by       = :current_user_id,
    updated_at       = :now
WHERE id = :staff_id AND hub_id = :hub_id AND is_deleted = 0;
