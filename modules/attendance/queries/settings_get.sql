-- Configuración de fichajes del hub (singleton). Runtime inyecta :hub_id.
-- Portado de AttendanceService.get_settings. Si no hay fila, el SDK/UI aplica
-- los valores por defecto (foto off, entrada manual on, umbrales 15/15, auto-cierre 12h).
SELECT id, require_photo, allow_manual_entry, late_threshold_minutes,
       early_departure_minutes, auto_clock_out_hours
FROM attendance_settings
WHERE hub_id = :hub_id AND is_deleted = 0
LIMIT 1;
