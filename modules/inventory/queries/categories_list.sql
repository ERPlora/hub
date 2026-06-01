-- Categorías activas con conteo de productos activos. Portado de CategoryService.list_categories
-- (orden por order, name; product_count = nº de productos activos vinculados vía M2M).
SELECT c.id, c.name, c.slug, c.icon, c.color, c."order",
       (SELECT COUNT(*)
        FROM inventory_product_categories pc
        JOIN inventory_product p ON p.id = pc.product_id
        WHERE pc.category_id = c.id AND p.is_active = 1 AND p.is_deleted = 0) AS product_count
FROM inventory_category c
WHERE c.hub_id = :hub_id AND c.is_deleted = 0 AND c.is_active = 1
ORDER BY c."order" ASC, c.name ASC;
