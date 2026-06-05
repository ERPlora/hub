-- Lista de centros de producción del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de WorkCenterService.list_centers. :active_only (1 = solo activos, 0 = todos) y
-- :center_type ('' = sin filtro) los pasa el SDK/UI.
SELECT id, code, name, center_type, capacity_per_hour, hourly_cost,
       location_ref, is_active, calendar, notes, created_at
FROM work_centers_center
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = 0 OR is_active = 1)
  AND (:center_type = '' OR center_type = :center_type)
ORDER BY code ASC;
