-- Categorías de servicios activas con conteo de servicios activos. Portado de
-- CategoryService.list_categories (orden por sort_order, name).
SELECT c.id, c.name, c.slug, c.icon, c.color, c.parent_id, c.sort_order,
       (SELECT COUNT(*)
        FROM services_service s
        WHERE s.category_id = c.id AND s.is_active = 1 AND s.is_deleted = 0) AS service_count
FROM services_category c
WHERE c.hub_id = :hub_id AND c.is_deleted = 0 AND c.is_active = 1
ORDER BY c.sort_order ASC, c.name ASC;
