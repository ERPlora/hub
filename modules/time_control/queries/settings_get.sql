-- Ajustes de control horario del hub (singleton). Runtime inyecta :hub_id.
-- Portado de TimeControlService.get_settings. Si no hay fila, el SDK/UI aplica defaults.
SELECT id, geolocation_enabled, geolocation_required, geofence_radius_meters,
       auto_clock_out_enabled, auto_clock_out_hours, allow_manual_records,
       require_notes_manual, data_retention_months
FROM time_control_settings
WHERE hub_id = :hub_id AND is_deleted = 0
LIMIT 1;
