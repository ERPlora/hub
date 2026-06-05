-- Posiciones de stock en un bin concreto. Runtime inyecta :hub_id.
-- Portado de LocationService.get_stock_at_bin.
SELECT id, bin_id, product_ref, lot_ref, quantity, last_count_at
FROM locations_stock_position
WHERE hub_id = :hub_id AND is_deleted = 0
  AND bin_id = :bin_id
ORDER BY product_ref ASC, lot_ref ASC;
