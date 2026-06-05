-- Un centro de producción por id. Runtime inyecta :hub_id.
-- Portado de WorkCenterService.get_center.
SELECT id, code, name, center_type, capacity_per_hour, hourly_cost,
       location_ref, is_active, calendar, notes, created_at
FROM work_centers_center
WHERE id = :id AND hub_id = :hub_id AND is_deleted = 0;
