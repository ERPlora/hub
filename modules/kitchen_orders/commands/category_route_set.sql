-- Upsert de enrutado categoría → estación. Runtime inyecta :new_id, :hub_id,
-- :current_user_id, :now. Portado de KitchenStationService.set_routing (rama category_id).
-- (category_id único por hub: uq_..._category_station_hub_category.)
INSERT INTO kitchen_orders_category_station
  (id, hub_id, category_id, station_id, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :category_id, :station_id, 0, :current_user_id, :current_user_id, :now, :now)
ON CONFLICT (hub_id, category_id) DO UPDATE SET
  station_id = excluded.station_id,
  is_deleted = 0,
  updated_by = :current_user_id,
  updated_at = :now;
