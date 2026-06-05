-- Detalle de un repartidor. Runtime inyecta :hub_id.
-- Portado de DeliveryService.get_driver.
SELECT id, name, phone, vehicle_type, is_active, is_external, notes
FROM delivery_driver
WHERE id = :driver_id AND hub_id = :hub_id AND is_deleted = 0;
