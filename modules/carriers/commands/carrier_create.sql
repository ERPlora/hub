-- Alta de transportista. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de CarriersService.create_carrier. La unicidad de (hub_id, code) la garantiza
-- el índice uq_carrier_hub_code. service_types/max_dimensions llegan ya serializados a JSON-TEXT.
INSERT INTO carriers_carrier
  (id, hub_id, code, name, provider, service_types, is_active,
   account_credentials_hash, supports_pickup, supports_tracking,
   max_weight_kg, max_dimensions,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :provider, :service_types, 1,
   :account_credentials_hash, :supports_pickup, :supports_tracking,
   :max_weight_kg, :max_dimensions,
   0, :current_user_id, :current_user_id, :now, :now);
