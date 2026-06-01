-- Incrementa el stock de un producto existente por :qty (recepción de mercancía).
-- Lo emite el handler WASM receive_stock, una op por línea casada por id. Si :unit_cost
-- viene informado, también actualiza el coste. Portado de ProductService.receive_stock.
UPDATE inventory_product
SET stock = stock + :qty,
    cost = CASE WHEN :unit_cost IS NOT NULL THEN :unit_cost ELSE cost END,
    updated_by = :current_user_id, updated_at = :now
WHERE id = :product_id AND hub_id = :hub_id AND is_deleted = 0;
