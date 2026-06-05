-- Líneas de una comanda concreta. Runtime inyecta :hub_id.
-- Portado de OrderService.get_order (sección items). station_id se resuelve en UI/SDK.
SELECT id, order_id, station_id, product_id, product_name,
       unit_price, quantity, total, modifiers, notes,
       status, seat_number, fired_at, started_at, completed_at
FROM kitchen_orders_order_item
WHERE hub_id = :hub_id AND is_deleted = 0
  AND order_id = :order_id
ORDER BY created_at ASC;
