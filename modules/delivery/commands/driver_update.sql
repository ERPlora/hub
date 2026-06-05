-- Actualización de repartidor. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de DeliveryService.update_driver. El patch (valores actuales para campos no
-- provistos) lo resuelve el runtime antes de ejecutar; todos los binds son requeridos.
UPDATE delivery_driver
SET name         = :name,
    phone        = :phone,
    vehicle_type = :vehicle_type,
    is_active    = :is_active,
    is_external  = :is_external,
    notes        = :notes,
    updated_by   = :current_user_id,
    updated_at   = :now
WHERE id = :driver_id AND hub_id = :hub_id AND is_deleted = 0;
