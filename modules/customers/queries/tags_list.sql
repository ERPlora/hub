-- Etiquetas del hub. Portado de TagService.list_tags.
SELECT id, name, color, is_active
FROM customers_customertag
WHERE hub_id = :hub_id AND is_deleted = 0 AND is_active = 1
ORDER BY name ASC;
