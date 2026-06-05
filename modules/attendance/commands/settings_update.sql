-- Actualización de la configuración de fichajes del hub (singleton).
-- Portado de AttendanceService.update_settings. Runtime inyecta :hub_id,
-- :current_user_id, :now. Sólo sobreescribe el campo si el bind no es NULL
-- (COALESCE conserva el valor actual cuando no se envía).
-- get_or_create: si no existe fila, el runtime usa attendance._insert_settings.
UPDATE attendance_settings
SET require_photo           = COALESCE(:require_photo, require_photo),
    allow_manual_entry      = COALESCE(:allow_manual_entry, allow_manual_entry),
    late_threshold_minutes  = COALESCE(:late_threshold_minutes, late_threshold_minutes),
    early_departure_minutes = COALESCE(:early_departure_minutes, early_departure_minutes),
    auto_clock_out_hours    = COALESCE(:auto_clock_out_hours, auto_clock_out_hours),
    updated_by              = :current_user_id,
    updated_at              = :now
WHERE hub_id = :hub_id AND is_deleted = 0;
