-- Alta de zona dentro de un almacén. Runtime inyecta :new_id, :hub_id,
-- :current_user_id, :now. Portado de LocationService.create_zone.
-- (hub_id, warehouse_id, code) único lo garantiza uq_locations_zone_wh_code.
-- La validación de zone_type ∈ {storage,picking,packing,receiving,shipping} la hace
-- el JSON Schema (enum). La existencia del warehouse la garantiza la FK.
INSERT INTO locations_zone
  (id, hub_id, warehouse_id, code, name, zone_type, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :warehouse_id, :code, :name, :zone_type, 1,
   0, :current_user_id, :current_user_id, :now, :now);
