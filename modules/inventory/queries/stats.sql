-- Métricas de inventario del hub (dashboard): nº productos, en stock, stock bajo, valor total.
-- Portado del dashboard de routes.py (total_products, products_in_stock, low_stock, value).
SELECT
  COUNT(*)                                                          AS total_products,
  COALESCE(SUM(CASE WHEN stock > 0 THEN 1 ELSE 0 END), 0)           AS products_in_stock,
  COALESCE(SUM(CASE WHEN stock <= low_stock_threshold THEN 1 ELSE 0 END), 0) AS products_low_stock,
  COALESCE(SUM(price * stock), 0)                                   AS total_inventory_value
FROM inventory_product
WHERE hub_id = :hub_id AND is_deleted = 0 AND is_active = 1;
