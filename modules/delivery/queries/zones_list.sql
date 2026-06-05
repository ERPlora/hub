-- Zonas de reparto del hub. Runtime inyecta :hub_id.
-- Portado de DeliveryService.list_zones. :active_only ('' = todas, '1' = solo activas).
SELECT id, name, is_active, min_order, delivery_fee, estimated_time,
       zip_codes, max_radius_km, sort_order
FROM delivery_zone
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = '' OR is_active = 1)
ORDER BY sort_order ASC, name ASC;
