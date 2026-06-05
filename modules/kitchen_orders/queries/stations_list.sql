-- Estaciones de producción del hub. Runtime inyecta :hub_id.
-- Portado de KitchenStationService.list_stations. El recuento de líneas pendientes
-- por estación (pending_count) se calcula vía la query items_pending_by_station.
-- (Bind :is_active: '' = todas, '1' = solo activas, '0' = solo inactivas.)
SELECT id, name, name_es, description, color, icon,
       printer_name, sort_order, is_active
FROM kitchen_orders_station
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:is_active = '' OR is_active = :is_active)
ORDER BY sort_order ASC, name ASC;
