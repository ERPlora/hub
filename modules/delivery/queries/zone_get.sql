-- Detalle de una zona de reparto. Runtime inyecta :hub_id.
-- Portado de DeliveryService.get_zone.
SELECT id, name, is_active, min_order, delivery_fee, estimated_time,
       zip_codes, max_radius_km, sort_order
FROM delivery_zone
WHERE id = :zone_id AND hub_id = :hub_id AND is_deleted = 0;
