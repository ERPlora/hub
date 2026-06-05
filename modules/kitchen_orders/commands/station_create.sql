-- Alta de estación de producción. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de KitchenStationService.create_station. (name único por hub: uq_..._station_hub_name.)
INSERT INTO kitchen_orders_station
  (id, hub_id, name, name_es, description, color, icon, printer_name,
   sort_order, is_active, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :name_es, :description, :color, :icon, :printer_name,
   :sort_order, 1, 0, :current_user_id, :current_user_id, :now, :now);
