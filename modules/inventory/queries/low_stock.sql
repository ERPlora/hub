-- Productos activos en o por debajo de su umbral de stock bajo (orden por stock asc).
-- Portado de ProductService.list_low_stock (is_low_stock = stock <= low_stock_threshold).
SELECT id, name, sku, stock, low_stock_threshold
FROM inventory_product
WHERE hub_id = :hub_id AND is_deleted = 0 AND is_active = 1
  AND stock <= low_stock_threshold
ORDER BY stock ASC
LIMIT 50;
