-- Un paquete por id (scope hub_id). Portado de PackageService.get_package
-- (las líneas se piden aparte con services.package_items.list).
SELECT id, name, slug, description, discount_type, discount_value, fixed_price,
       validity_days, max_uses, is_active, is_featured
FROM services_package
WHERE id = :package_id AND hub_id = :hub_id AND is_deleted = 0;
