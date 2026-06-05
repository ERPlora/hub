-- Alta de servicio. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de ServiceCatalogService.create_service. El slug lo calcula el SDK/handler.
INSERT INTO services_service
  (id, hub_id, name, slug, description, short_description, category_id,
   pricing_type, price, cost, duration_minutes, buffer_before, buffer_after,
   max_capacity, is_bookable, requires_confirmation, allow_online_booking,
   sort_order, is_active, is_featured, sku, barcode, notes,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :slug, :description, :short_description, :category_id,
   :pricing_type, :price, :cost, :duration_minutes, :buffer_before, :buffer_after,
   :max_capacity, :is_bookable, :requires_confirmation, :allow_online_booking,
   :sort_order, 1, :is_featured, :sku, :barcode, :notes,
   0, :current_user_id, :current_user_id, :now, :now);
