-- Tarifas horarias activas del hub. Runtime inyecta :hub_id.
-- Portado de TimesheetService.list_hourly_rates. Orden por nombre.
SELECT id, name, rate, employee_id, is_default, is_active
FROM timesheets_hourly_rate
WHERE hub_id = :hub_id AND is_deleted = 0 AND is_active = 1
ORDER BY name ASC;
