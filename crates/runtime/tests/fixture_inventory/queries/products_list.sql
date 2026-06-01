SELECT id, name, sku, price, stock FROM products
WHERE hub_id = :hub_id AND is_deleted = 0 ORDER BY name ASC;
