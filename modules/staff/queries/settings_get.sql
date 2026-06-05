-- Configuración singleton de staff del hub. Runtime inyecta :hub_id.
SELECT id, default_work_start, default_work_end, default_break_duration,
       min_advance_booking, max_daily_hours, overtime_threshold,
       show_staff_photos, show_staff_bio, allow_staff_selection,
       notify_new_appointment, notify_cancellation
FROM staff_settings
WHERE hub_id = :hub_id AND is_deleted = 0
LIMIT 1;
