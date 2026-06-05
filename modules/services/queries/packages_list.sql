-- Lista de paquetes del hub con nº de líneas activas. Portado de PackageService.list_packages
-- (orden por sort_order, name). El filtro is_active opcional se aplica en UI/SDK.
SELECT p.id, p.name, p.slug, p.discount_type, p.discount_value, p.fixed_price, p.is_active,
       (SELECT COUNT(*)
        FROM services_packageitem i
        WHERE i.package_id = p.id AND i.is_deleted = 0) AS items
FROM services_package p
WHERE p.hub_id = :hub_id AND p.is_deleted = 0
ORDER BY p.sort_order ASC, p.name ASC;
