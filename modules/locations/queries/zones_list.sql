-- Zonas de un almacén (filtro opcional por zone_type). Runtime inyecta :hub_id.
-- Portado de LocationService.list_zones. (:zone_type = '' → sin filtro.)
SELECT id, warehouse_id, code, name, zone_type, is_active, created_at
FROM locations_zone
WHERE hub_id = :hub_id AND is_deleted = 0
  AND warehouse_id = :warehouse_id
  AND (:zone_type = '' OR zone_type = :zone_type)
ORDER BY code ASC;
