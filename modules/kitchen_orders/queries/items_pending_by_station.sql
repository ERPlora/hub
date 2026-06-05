-- Recuento de líneas en curso (pending/preparing) por estación. Runtime inyecta :hub_id.
-- Portado del pending_count de KitchenStationService.list_stations.
SELECT station_id, COUNT(*) AS pending_count
FROM kitchen_orders_order_item
WHERE hub_id = :hub_id AND is_deleted = 0
  AND status IN ('pending', 'preparing')
  AND station_id IS NOT NULL
GROUP BY station_id;
