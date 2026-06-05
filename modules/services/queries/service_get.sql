-- Un servicio por id (scope hub_id). Portado de ServiceCatalogService.get_service.
SELECT id, name, slug, description, short_description, category_id,
       pricing_type, price, min_price, max_price, cost, tax_rate,
       duration_minutes, buffer_before, buffer_after, max_capacity,
       image, icon, color, is_bookable, requires_confirmation,
       allow_online_booking, sort_order, is_active, is_featured, sku, barcode, notes
FROM services_service
WHERE id = :service_id AND hub_id = :hub_id AND is_deleted = 0;
