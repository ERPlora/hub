-- Líneas (servicios) de un paquete. Portado del bloque items[] de PackageService.get_package.
SELECT i.service_id, i.quantity, i.sort_order, s.name AS service_name, s.price AS service_price
FROM services_packageitem i
JOIN services_service s ON s.id = i.service_id AND s.is_deleted = 0
WHERE i.package_id = :package_id AND i.hub_id = :hub_id AND i.is_deleted = 0
ORDER BY i.sort_order ASC;
