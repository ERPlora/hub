-- Alta de fila de tarifario para un transportista. Runtime inyecta :new_id, :hub_id,
-- :current_user_id, :now. Portado de CarriersService.add_rate. La validación de que el
-- carrier existe, el rango de peso (weight_to >= weight_from) y la normalización de país
-- a mayúsculas las aplica el SDK/WASM — ver WASM-TODO.
INSERT INTO carriers_shipping_rate
  (id, hub_id, carrier_id, service_type, origin_country, destination_country,
   weight_from_kg, weight_to_kg, price, currency,
   delivery_days_min, delivery_days_max, valid_from, valid_until,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :carrier_id, :service_type, :origin_country, :destination_country,
   :weight_from_kg, :weight_to_kg, :price, :currency,
   :delivery_days_min, :delivery_days_max, :valid_from, :valid_until,
   0, :current_user_id, :current_user_id, :now, :now);
