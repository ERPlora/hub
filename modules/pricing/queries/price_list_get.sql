-- Una lista de precios por id (scope hub_id). Portado de PricingService.get_price_list (cabecera).
SELECT id, code, name, currency, is_default, is_active, valid_from, valid_until, segment
FROM pricing_price_list
WHERE id = :price_list_id AND hub_id = :hub_id AND is_deleted = 0;
