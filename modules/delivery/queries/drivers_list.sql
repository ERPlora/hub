-- Repartidores del hub. Runtime inyecta :hub_id.
-- Portado de DeliveryService.list_drivers. :active_only ('' = todos, '1' = solo activos).
SELECT id, name, phone, vehicle_type, is_active, is_external, notes
FROM delivery_driver
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = '' OR is_active = 1)
ORDER BY name ASC;
