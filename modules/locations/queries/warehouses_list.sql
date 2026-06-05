-- Almacenes del hub. Runtime inyecta :hub_id. Portado de LocationService.list_warehouses.
-- :active_only ('1' = solo activos, '' = todos) lo aplica el filtro; orden por code.
SELECT id, code, name, address, is_active, is_default, created_at
FROM locations_warehouse
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = '' OR is_active = 1)
ORDER BY code ASC;
