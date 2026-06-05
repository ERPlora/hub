-- Items de una lista de precios (scope hub_id). Portado de PricingService.get_price_list (items),
-- orden por product_ref y min_quantity.
SELECT id, price_list_id, product_ref, price, min_quantity, max_quantity
FROM pricing_price_list_item
WHERE price_list_id = :price_list_id AND hub_id = :hub_id AND is_deleted = 0
ORDER BY product_ref ASC, min_quantity ASC;
