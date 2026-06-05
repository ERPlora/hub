-- Actualización de tipo de ausencia. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de LeaveTypeService.update_leave_type. COALESCE permite parches parciales
-- (los binds opcionales llegan como NULL cuando no se quieren cambiar).
UPDATE leave_type
SET name          = COALESCE(:name, name),
    days_per_year = COALESCE(:days_per_year, days_per_year),
    is_paid       = COALESCE(:is_paid, is_paid),
    color         = COALESCE(:color, color),
    is_active     = COALESCE(:is_active, is_active),
    updated_by    = :current_user_id,
    updated_at    = :now
WHERE id = :leave_type_id AND hub_id = :hub_id AND is_deleted = 0;
