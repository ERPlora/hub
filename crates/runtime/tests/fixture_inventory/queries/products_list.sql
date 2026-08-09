SELECT id, name, sku, price, stock FROM inventory_product
WHERE hub_id = :hub_id AND is_deleted = 0 ORDER BY name ASC;
