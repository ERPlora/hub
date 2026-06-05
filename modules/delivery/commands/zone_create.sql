-- Alta de zona de reparto. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de DeliveryService.create_zone. zip_codes llega como string JSON ('[]' si vacío).
INSERT INTO delivery_zone
  (id, hub_id, name, min_order, delivery_fee, estimated_time, is_active,
   zip_codes, max_radius_km, sort_order,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :min_order, :delivery_fee, :estimated_time, :is_active,
   :zip_codes, :max_radius_km, :sort_order,
   0, :current_user_id, :current_user_id, :now, :now);
