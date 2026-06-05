-- Actualiza la configuración singleton de staff del hub. Runtime inyecta :hub_id,
-- :current_user_id, :now. Patrón COALESCE para actualización parcial.
-- El alta inicial del singleton (cuando aún no existe fila) la hace el runtime/seed.
UPDATE staff_settings
SET default_work_start     = COALESCE(:default_work_start, default_work_start),
    default_work_end       = COALESCE(:default_work_end, default_work_end),
    default_break_duration = COALESCE(:default_break_duration, default_break_duration),
    min_advance_booking    = COALESCE(:min_advance_booking, min_advance_booking),
    max_daily_hours        = COALESCE(:max_daily_hours, max_daily_hours),
    overtime_threshold     = COALESCE(:overtime_threshold, overtime_threshold),
    show_staff_photos      = COALESCE(:show_staff_photos, show_staff_photos),
    show_staff_bio         = COALESCE(:show_staff_bio, show_staff_bio),
    allow_staff_selection  = COALESCE(:allow_staff_selection, allow_staff_selection),
    notify_new_appointment = COALESCE(:notify_new_appointment, notify_new_appointment),
    notify_cancellation    = COALESCE(:notify_cancellation, notify_cancellation),
    updated_by             = :current_user_id,
    updated_at             = :now
WHERE hub_id = :hub_id AND is_deleted = 0;
