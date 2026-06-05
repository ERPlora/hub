-- Sedes del hub. Runtime inyecta :hub_id. Portado de LocationService.list_locations.
-- :active_only ('1' = solo activas, '' = todas) lo aplica el filtro opcional.
SELECT id, name, address, phone, email, manager_employee_id,
       timezone, color, is_active, sort_order
FROM workforce_planning_location
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = '' OR is_active = 1)
ORDER BY sort_order ASC, name ASC;
