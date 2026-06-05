-- Centros de trabajo activos del hub. Runtime inyecta :hub_id.
-- Portado de TimeControlService.list_workplaces.
SELECT id, name, address, latitude, longitude, radius_meters, is_active, is_default
FROM time_control_workplace
WHERE hub_id = :hub_id AND is_deleted = 0 AND is_active = 1
ORDER BY name ASC;
