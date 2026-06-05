-- Inserción de un servicio usada por el handler WASM batch (bulk_create_services).
-- El handler aporta :service_id (de new_ids), nombre, slug, precio, etc.
-- Runtime inyecta :hub_id, :current_user_id, :now.
INSERT INTO services_service
  (id, hub_id, name, slug, description, short_description, category_id,
   pricing_type, price, cost, duration_minutes, buffer_before, buffer_after,
   max_capacity, is_bookable, requires_confirmation, allow_online_booking,
   sort_order, is_active, is_featured, sku, barcode, notes,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:service_id, :hub_id, :name, :slug, :description, :short_description, :category_id,
   :pricing_type, :price, :cost, :duration_minutes, :buffer_before, :buffer_after,
   :max_capacity, :is_bookable, :requires_confirmation, :allow_online_booking,
   :sort_order, 1, :is_featured, :sku, :barcode, :notes,
   0, :current_user_id, :current_user_id, :now, :now);
