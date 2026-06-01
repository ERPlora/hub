-- Lista de productos activos del hub. Runtime inyecta :hub_id. (Búsqueda en UI/SDK.)
-- Portado de ProductService.list_products (active_only por defecto, orden por nombre).
SELECT id, name, sku, price, stock, is_active
FROM inventory_product
WHERE hub_id = :hub_id AND is_deleted = 0 AND is_active = 1
ORDER BY name ASC
LIMIT 50;
