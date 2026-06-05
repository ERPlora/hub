-- Lista de servicios activos del hub con nombre de categoría. Portado de
-- ServiceCatalogService.list_services (orden por sort_order, name; búsqueda/filtro en UI/SDK).
SELECT s.id, s.name, s.price, s.pricing_type, s.duration_minutes, s.is_bookable,
       s.category_id, c.name AS category
FROM services_service s
LEFT JOIN services_category c ON c.id = s.category_id AND c.is_deleted = 0
WHERE s.hub_id = :hub_id AND s.is_deleted = 0 AND s.is_active = 1
ORDER BY s.sort_order ASC, s.name ASC
LIMIT 50;
