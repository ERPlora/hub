-- Un producto por id (scope hub_id). Portado de ProductService.get_product.
SELECT id, name, sku, ean13, description, product_type, price, cost, stock,
       low_stock_threshold, tax_class_id, image, is_active
FROM inventory_product
WHERE id = :product_id AND hub_id = :hub_id AND is_deleted = 0;
