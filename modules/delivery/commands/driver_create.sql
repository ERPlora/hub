-- Alta de repartidor. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de DeliveryService.create_driver.
INSERT INTO delivery_driver
  (id, hub_id, name, phone, vehicle_type, is_active, is_external, notes,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :phone, :vehicle_type, :is_active, :is_external, :notes,
   0, :current_user_id, :current_user_id, :now, :now);
